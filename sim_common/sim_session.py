#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R21: long-lived grblHAL_sim process for host SIL layers that share flags.

protocol / integrity use:  -n -t 0 -p PORT
hardware_sim needs step logs (-s/-b/-r) → start its own sim; do not share.

grblHAL_sim is effectively single-TCP-session: clients must connect sequentially
(close previous client before next layer connects).
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .find_sim import find_sim
from .ports import find_free_port

FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
SESSION_PATH = RESULTS / "sim_session.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7681


@dataclass
class SimSession:
    host: str
    port: int
    mode: str  # "protocol"
    pid: int
    sim_path: str
    stderr_log: str

    def endpoint_args(self) -> list[str]:
        """CLI fragment: --host H --port P (no --start-sim)."""
        return ["--host", self.host, "--port", str(self.port)]


def start_protocol_session(
    preferred_port: int = DEFAULT_PORT,
    host: str = DEFAULT_HOST,
    boot_sleep: float = 0.9,
) -> SimSession:
    """
    Spawn grblHAL_sim for protocol-style TCP cases (-n -t 0).
    Caller must stop_session() in finally.
    """
    sim = find_sim()
    if not sim:
        raise FileNotFoundError(
            "grblHAL_sim not found (set GRBLHAL_SIM or vendor/grblhal_sim/bin)"
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    port = find_free_port(preferred_port, host=host)
    stderr_log = RESULTS / "sim_session_stderr.log"
    err_f = open(stderr_log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [str(sim), "-n", "-t", "0", "-p", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=err_f,
        cwd=str(sim.parent),
    )
    # Do not TCP-probe (single-session race); sleep then check alive
    time.sleep(boot_sleep)
    if proc.poll() is not None:
        try:
            err_f.close()
        except OSError:
            pass
        raise RuntimeError(
            f"sim exited early code={proc.returncode} log={stderr_log}"
        )
    sess = SimSession(
        host=host,
        port=port,
        mode="protocol",
        pid=int(proc.pid),
        sim_path=str(sim),
        stderr_log=str(stderr_log),
    )
    # stash proc on instance for stop (not in JSON)
    sess._proc = proc  # type: ignore[attr-defined]
    sess._err_f = err_f  # type: ignore[attr-defined]
    _write_session_meta(sess, running=True)
    return sess


def stop_session(sess: Optional[SimSession], timeout: float = 3.0) -> None:
    if sess is None:
        return
    proc = getattr(sess, "_proc", None)
    err_f = getattr(sess, "_err_f", None)
    if proc is not None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except OSError:
            pass
    if err_f is not None:
        try:
            err_f.close()
        except OSError:
            pass
    _write_session_meta(sess, running=False)


def _write_session_meta(sess: SimSession, running: bool) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    data = {
        "suite": "sim_session",
        "running": running,
        **{k: v for k, v in asdict(sess).items()},
    }
    SESSION_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_session_meta() -> Optional[dict]:
    if not SESSION_PATH.is_file():
        return None
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
