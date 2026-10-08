"""报告原子发布与门禁进程互斥；强停后留下running而不是旧pass。"""
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
import uuid


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class GateRun:
    def __init__(self, output: Path, lock_path: Path):
        self.output, self.lock_path = output, lock_path
        self.run_id = uuid.uuid4().hex
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.started = time.monotonic()
        self.lock = None
        self.published = False

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.lock_path.open("a+b")
        try:
            # 持续保留锁文件；删除已锁文件会让第二个进程锁到另一个inode。
            if self.lock.seek(0, os.SEEK_END) == 0:
                self.lock.write(b"0")
                self.lock.flush()
            self.lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            self.lock = None
            raise RuntimeError("另一个门禁正在运行，本次不修改其报告") from None
        try:
            self._state("running", "running", 1, [])
        except BaseException:
            self.lock.close()
            self.lock = None
            raise
        return self

    def _state(self, state, overall, code, failures):
        atomic_write_json(self.output, {
            "suite": "agent_gate", "run_id": self.run_id, "started_at": self.started_at,
            "generated_at": datetime.now(timezone.utc).isoformat(), "run_state": state,
            "overall_status": overall, "overall_exit": code,
            "duration_s": round(time.monotonic() - self.started, 2),
            "layers": failures, "failures": failures,
            "agent_hints": ["本轮尚未通过；修复异常后重新执行门禁"],
        })

    def publish(self, report):
        report.update(run_id=self.run_id, started_at=self.started_at, run_state="completed")
        atomic_write_json(self.output, report)
        self.published = True

    def __exit__(self, kind, value, traceback):
        try:
            if kind is not None or not self.published:
                detail = kind.__name__ if kind else "未发布完成报告"
                self._state("interrupted" if kind is KeyboardInterrupt else "failed", "fail",
                            130 if kind is KeyboardInterrupt else 1,
                            [{"id": "gate_runtime", "name": "gate_runtime", "status": "fail",
                              "blocking": True, "detail": detail}])
        finally:
            if self.lock:
                self.lock.close()
        return False
