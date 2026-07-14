#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal hardware-oriented sim runner (H-SIM-A baseline).

Starts vendored grblHAL_sim with optional step/block logs, runs motion cases,
checks MPos after simple moves. Not product firmware.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# local import (run from repo or hardware_sim/)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from step_oracle import (  # noqa: E402
    assert_travel_mm,
    max_abs_steps,
    parse_step_log,
)


FZ_ROOT = Path(__file__).resolve().parent.parent
HW_ROOT = Path(__file__).resolve().parent
RESULTS = HW_ROOT / "results"
CASES = HW_ROOT / "cases"
VENDOR_SIM = FZ_ROOT / "vendor" / "grblhal_sim" / "bin"
# grblHAL default $100/$101/$102 on this vendored build
DEFAULT_STEPS_PER_MM = (250.0, 250.0, 250.0)

OK_RE = re.compile(r"^ok\s*$", re.I)
ERROR_RE = re.compile(r"error:(\d+)", re.I)
ALARM_RE = re.compile(r"ALARM:(\d+)", re.I)
MPOS_RE = re.compile(r"MPos:([-\d.]+),([-\d.]+),([-\d.]+)")


def find_sim() -> Optional[Path]:
    env = os.environ.get("GRBLHAL_SIM")
    if env and Path(env).is_file():
        return Path(env)
    for name in ("grblHAL_sim.exe", "grblHAL_sim"):
        p = VENDOR_SIM / name
        if p.is_file():
            return p
    return None


@dataclass
class CaseResult:
    name: str
    passed: bool
    detail: str = ""
    mpos: Optional[List[float]] = None
    responses: List[str] = field(default_factory=list)


class GrblTcp:
    def __init__(self, host: str, port: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._buf = b""

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        time.sleep(0.8)
        self._drain()

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _drain(self) -> List[str]:
        lines: List[str] = []
        if not self.sock:
            return lines
        self.sock.settimeout(0.12)
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
                while b"\n" in self._buf:
                    raw, self._buf = self._buf.split(b"\n", 1)
                    t = raw.decode("utf-8", errors="replace").strip("\r")
                    if t:
                        lines.append(t)
        except (socket.timeout, BlockingIOError):
            pass
        finally:
            if self.sock:
                self.sock.settimeout(self.timeout)
        return lines

    def send_line(self, line: str, wait: float = 2.0) -> List[str]:
        assert self.sock
        self.sock.sendall((line.rstrip("\r\n") + "\n").encode("utf-8"))
        deadline = time.time() + wait
        collected: List[str] = []
        while time.time() < deadline:
            got = self._drain()
            collected.extend(got)
            if any(OK_RE.match(x) or ERROR_RE.search(x) or ALARM_RE.search(x) for x in got):
                time.sleep(0.05)
                collected.extend(self._drain())
                break
            time.sleep(0.05)
        return collected

    def soft_reset(self) -> None:
        assert self.sock
        self.sock.sendall(b"\x18")
        time.sleep(0.5)
        self._drain()

    def unlock(self) -> None:
        self.send_line("$X", wait=1.5)
        self.send_line("G21 G90 G94", wait=1.0)


def parse_mpos(responses: Sequence[str]) -> Optional[List[float]]:
    for r in responses:
        m = MPOS_RE.search(r)
        if m:
            return [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    return None


def wait_idle(client: GrblTcp, timeout: float = 30.0) -> Tuple[Optional[List[float]], List[str]]:
    """Poll ? until Idle (or timeout). Returns (mpos, responses)."""
    deadline = time.time() + timeout
    collected: List[str] = []
    last_mpos: Optional[List[float]] = None
    while time.time() < deadline:
        resp = client.send_line("?", wait=0.8)
        collected.extend(resp)
        m = parse_mpos(resp)
        if m:
            last_mpos = m
        joined = " ".join(resp)
        if "<Idle" in joined or any(x.startswith("<Idle") for x in resp):
            return last_mpos, collected
        time.sleep(0.1)
    return last_mpos, collected


def run_motion_case(
    client: GrblTcp,
    name: str,
    moves: Sequence[str],
    expect_delta: Sequence[float],
    eps: float = 0.25,
) -> CaseResult:
    """Assert MPos delta after moves (machine coords are sticky across cases)."""
    client.soft_reset()
    client.unlock()
    all_resp: List[str] = []
    start, r0 = wait_idle(client, timeout=5.0)
    all_resp.extend(r0)
    if start is None:
        start = [0.0, 0.0, 0.0]
    for mv in moves:
        resp = client.send_line(mv, wait=15.0)
        all_resp.extend(resp)
        if any(ERROR_RE.search(x) or ALARM_RE.search(x) for x in resp):
            return CaseResult(name=name, passed=False, detail=f"error on {mv}: {resp}", responses=all_resp)
        if not any(OK_RE.match(x) for x in resp):
            return CaseResult(name=name, passed=False, detail=f"no ok for {mv}: {resp}", responses=all_resp)
    mpos, r1 = wait_idle(client, timeout=30.0)
    all_resp.extend(r1)
    if mpos is None:
        return CaseResult(name=name, passed=False, detail="no MPos after idle wait", responses=all_resp)
    delta = [mpos[i] - start[i] for i in range(3)]
    for a, b in zip(delta, expect_delta):
        if abs(a - b) > eps:
            return CaseResult(
                name=name,
                passed=False,
                detail=f"delta {delta} != expected {list(expect_delta)} (start={start}, mpos={mpos})",
                mpos=mpos,
                responses=all_resp,
            )
    return CaseResult(name=name, passed=True, mpos=mpos, responses=all_resp)


def run_error_case(client: GrblTcp, name: str, line: str, expect_error: bool = True) -> CaseResult:
    client.soft_reset()
    client.unlock()
    # leave feed unset for undefined feed test
    if "undefined_feed" in name:
        resp = client.send_line("G1 X1 Y0", wait=2.0)
    else:
        resp = client.send_line(line, wait=2.0)
    has_err = any(ERROR_RE.search(x) or ALARM_RE.search(x) for x in resp)
    ok = has_err if expect_error else any(OK_RE.match(x) for x in resp)
    return CaseResult(
        name=name,
        passed=ok,
        detail="" if ok else f"resp={resp}",
        responses=resp,
    )


def run_settings_travel_roundtrip(client: GrblTcp) -> CaseResult:
    """$130 max travel set/get (soft-limit enforcement is unreliable on sim without full homing plant)."""
    client.soft_reset()
    client.unlock()
    resp: List[str] = []
    for line in ("$130=80.0", "$131=80.0", "$132=80.0"):
        r = client.send_line(line, wait=1.0)
        resp.extend(r)
        if not any(OK_RE.match(x) for x in r):
            return CaseResult("settings_max_travel_set", False, f"set failed {line}: {r}", responses=resp)
    r = client.send_line("$130", wait=1.0)
    resp.extend(r)
    joined = "\n".join(r)
    if "$130=80" not in joined.replace(" ", ""):
        # allow $130=80.000
        if not re.search(r"\$130=80(\.0+)?\b", joined):
            return CaseResult(
                "settings_max_travel_roundtrip",
                False,
                f"readback missing 80: {r}",
                responses=resp,
            )
    return CaseResult("settings_max_travel_roundtrip", True, responses=resp)


def run_soft_limit_setting_gate(client: GrblTcp) -> CaseResult:
    """
    Document sim behavior: $20=1 without homing often error:10 (Grbl rule).
    We assert that enabling soft limits without homing is rejected OR accepted
    only after $22=1 — and we never claim product soft-limit equivalence.
    """
    client.soft_reset()
    client.unlock()
    # ensure homing off
    client.send_line("$22=0", wait=1.0)
    r = client.send_line("$20=1", wait=1.0)
    # classic: error:10 Soft limits require homing
    if any(ERROR_RE.search(x) for x in r):
        return CaseResult(
            "soft_limit_requires_homing",
            True,
            detail="sim rejects $20 without homing (error) — expected community rule",
            responses=r,
        )
    # if accepted, require $22 first path works
    client.send_line("$20=0", wait=0.5)
    client.send_line("$22=1", wait=0.5)
    r2 = client.send_line("$20=1", wait=1.0)
    ok = any(OK_RE.match(x) for x in r2)
    return CaseResult(
        "soft_limit_requires_homing",
        ok,
        detail="" if ok else f"could not enable soft limits: {r} / {r2}",
        responses=list(r) + list(r2),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="hardware_sim baseline runner")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7682)
    ap.add_argument("--start-sim", action="store_true")
    ap.add_argument("--time-factor", type=float, default=0.0, help="grblHAL -t (0=fast)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    RESULTS.mkdir(parents=True, exist_ok=True)
    step_log = RESULTS / "step_last.log"
    block_log = RESULTS / "block_last.log"
    eeprom = RESULTS / "EEPROM_hw.DAT"

    sim_proc: Optional[subprocess.Popen] = None
    if args.start_sim:
        sim = find_sim()
        if not sim:
            print("ERROR: grblHAL_sim not found", file=sys.stderr)
            return 2
        # -r must be >0 or step printing is disabled (upstream default 0=no print)
        cmd = [
            str(sim),
            "-n",
            "-t",
            str(args.time_factor),
            "-r",
            "0.001",
            "-p",
            str(args.port),
            "-s",
            str(step_log),
            "-b",
            str(block_log),
            "-e",
            str(eeprom),
        ]
        sim_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2)

    client = GrblTcp(args.host, args.port)
    results: List[CaseResult] = []
    try:
        try:
            client.connect()
        except OSError as exc:
            print(f"ERROR: connect {args.host}:{args.port}: {exc}", file=sys.stderr)
            return 2

        results.append(
            run_motion_case(
                client,
                "move_x_10",
                ["G91", "G1 X10 Y0 F1000", "G90"],
                expect_delta=(10.0, 0.0, 0.0),
                eps=0.15,
            )
        )
        results.append(
            run_motion_case(
                client,
                "move_xy_delta",
                ["G91", "G1 X5 Y5 F1000", "G90"],
                expect_delta=(5.0, 5.0, 0.0),
                eps=0.15,
            )
        )
        results.append(run_error_case(client, "undefined_feed_G1", "G1 X1"))
        results.append(run_settings_travel_roundtrip(client))
        results.append(run_soft_limit_setting_gate(client))
    finally:
        client.close()
        if sim_proc is not None:
            time.sleep(0.3)
            sim_proc.terminate()
            try:
                sim_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sim_proc.kill()

    # step log: check after process exit (flush) + StepOracle
    if args.start_sim:
        step_ok = step_log.is_file() and step_log.stat().st_size > 0
        block_ok = block_log.is_file() and block_log.stat().st_size > 0
        results.append(
            CaseResult(
                name="step_log_nonempty",
                passed=step_ok,
                detail="" if step_ok else f"missing/empty {step_log} (need -r >0)",
            )
        )
        results.append(
            CaseResult(
                name="block_log_nonempty",
                passed=block_ok,
                detail="" if block_ok else f"missing/empty {block_log}",
            )
        )
        samples = parse_step_log(step_log)
        mx = max_abs_steps(samples)
        # Session motions: +10 X then +5 X +5 Y => ~15mm X, ~5mm Y at 250 step/mm
        ok, detail, actual_mm = assert_travel_mm(
            mx,
            expect_mm=(15.0, 5.0, 0.0),
            steps_per_mm=DEFAULT_STEPS_PER_MM,
            eps_mm=1.0,
        )
        results.append(
            CaseResult(
                name="step_oracle_session_travel",
                passed=ok and step_ok,
                detail=detail if not ok else f"mm≈{actual_mm} steps={mx}",
            )
        )

    failed = [r for r in results if not r.passed]
    print("=== hardware_sim report ===")
    for r in results:
        print(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}" + (f" — {r.detail}" if r.detail else ""))
        if r.mpos:
            print(f"           MPos={r.mpos}")
    report = {
        "sim_mode": "hardware_sim_not_silicon",
        "engine": "grblHAL_sim",
        "step_log": str(step_log) if step_log.is_file() else None,
        "block_log": str(block_log) if block_log.is_file() else None,
        "cases": [asdict(r) for r in results],
    }
    out = RESULTS / "last_hw_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
