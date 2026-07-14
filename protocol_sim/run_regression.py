#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC-side protocol regression against grblHAL Simulator (or any TCP Grbl-like endpoint).

Official sim: https://github.com/grblHAL/Simulator
Web Builder:  https://svn.io-engineering.com:8443/?driver=Simulator

This does NOT run Grbl_Esp32 firmware. It checks generic Grbl/grblHAL ok/error/ALARM
behavior for G-code programs on a desktop simulator.
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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parent
FZ_ROOT = ROOT.parent
CASES = ROOT / "cases"
PASS_DIR = CASES / "pass"
FAIL_DIR = CASES / "fail"
RESULTS_DIR = ROOT / "results"
# Optional product firmware tree (env GRBL_ROOT) for soft repo tests
_GRBL = os.environ.get("GRBL_ROOT", "")
REPO_ROOT = Path(_GRBL) if _GRBL else FZ_ROOT
REPO_TESTS = (
    Path(_GRBL) / "Grbl_Esp32" / "src" / "tests"
    if _GRBL
    else FZ_ROOT / "fixtures" / "grbl_tests"
)
VENDOR_SIM = FZ_ROOT / "vendor" / "grblhal_sim" / "bin"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7681
DEFAULT_TIMEOUT = 5.0
BOOT_WAIT = 0.8

ERROR_RE = re.compile(r"error:(\d+)", re.I)
ALARM_RE = re.compile(r"ALARM:(\d+)", re.I)
OK_RE = re.compile(r"^ok\s*$", re.I)


@dataclass
class LineResult:
    line: str
    responses: List[str]
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    name: str
    kind: str  # pass | fail | soft
    passed: bool
    detail: str = ""
    lines: List[LineResult] = field(default_factory=list)


def _env_exe(name: str, default: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    # Search PATH
    from shutil import which

    w = which(default)
    return Path(w) if w else None


def find_sim() -> Optional[Path]:
    for cand in (
        _env_exe("GRBLHAL_SIM", "grblHAL_sim.exe"),
        _env_exe("GRBLHAL_SIM", "grblHAL_sim"),
        VENDOR_SIM / "grblHAL_sim.exe",
        VENDOR_SIM / "grblHAL_sim",
    ):
        if cand is not None and Path(cand).is_file():
            return Path(cand)
    return None


def find_validator() -> Optional[Path]:
    for cand in (
        _env_exe("GRBLHAL_VALIDATOR", "grblHAL_validator.exe"),
        _env_exe("GRBLHAL_VALIDATOR", "grblHAL_validator"),
        VENDOR_SIM / "grblHAL_validator.exe",
        VENDOR_SIM / "grblHAL_validator",
    ):
        if cand is not None and Path(cand).is_file():
            return Path(cand)
    return None


class GrblTcpClient:
    """Minimal line-oriented Grbl client over TCP (sim -p port)."""

    def __init__(self, host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._buf = b""

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        # Drain boot banner
        time.sleep(BOOT_WAIT)
        self._drain(quiet=True)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _drain(self, quiet: bool = False) -> List[str]:
        lines: List[str] = []
        if not self.sock:
            return lines
        self.sock.settimeout(0.15)
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
                while b"\n" in self._buf:
                    raw, self._buf = self._buf.split(b"\n", 1)
                    text = raw.decode("utf-8", errors="replace").strip("\r")
                    if text:
                        lines.append(text)
        except (socket.timeout, BlockingIOError):
            pass
        finally:
            if self.sock:
                self.sock.settimeout(self.timeout)
        return lines

    def send_line(self, line: str, wait: float = 0.5) -> List[str]:
        if not self.sock:
            raise RuntimeError("not connected")
        payload = (line.rstrip("\r\n") + "\n").encode("utf-8")
        self.sock.sendall(payload)
        deadline = time.time() + max(wait, 0.1)
        collected: List[str] = []
        while time.time() < deadline:
            got = self._drain()
            collected.extend(got)
            # Stop early on terminal reply
            if any(OK_RE.match(x) or ERROR_RE.search(x) or ALARM_RE.search(x) for x in got):
                # small extra drain for multi-line replies
                time.sleep(0.05)
                collected.extend(self._drain())
                break
            time.sleep(0.05)
        return collected

    def soft_reset(self) -> List[str]:
        if not self.sock:
            raise RuntimeError("not connected")
        self.sock.sendall(b"\x18")  # Ctrl-X
        time.sleep(0.4)
        return self._drain()

    def unlock_if_needed(self) -> None:
        # Common post-boot: alarm state; $X unlocks on many Grbl builds
        self.send_line("$X", wait=1.0)
        self.send_line("G21 G90 G94", wait=1.0)
        # Prefer work-offset zero; ignore failure (some builds reject L20 form)
        self.send_line("G10 L20 P1 X0 Y0 Z0", wait=1.0)


def is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith(";") or s.startswith("(")


def classify_responses(responses: Sequence[str]) -> Tuple[str, Optional[str]]:
    """
    Returns (kind, code) where kind in ok|error|alarm|status|unknown
    """
    for r in responses:
        m = ERROR_RE.search(r)
        if m:
            return "error", m.group(1)
        m = ALARM_RE.search(r)
        if m:
            return "alarm", m.group(1)
    for r in responses:
        if OK_RE.match(r):
            return "ok", None
    for r in responses:
        if r.startswith("<") and r.endswith(">"):
            return "status", None
        if r.startswith("["):
            return "status", None
    return "unknown", None


def run_pass_file(client: GrblTcpClient, path: Path) -> CaseResult:
    name = path.name
    results: List[LineResult] = []
    client.soft_reset()
    client.unlock_if_needed()
    failed = False
    detail = ""
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        if is_comment_or_blank(raw):
            continue
        # Skip pure settings reset noise if present
        line = raw.strip()
        # Motion/spindle lines may take longer if sim runs at realtime (-t 1).
        wait = 15.0 if re.match(r"(?i)^[GM]\d", line) else 2.0
        resp = client.send_line(line, wait=wait)
        kind, code = classify_responses(resp)
        ok = kind == "ok"
        if kind in ("error", "alarm"):
            ok = False
            failed = True
            detail = f"unexpected {kind}:{code} on: {line}"
        elif kind != "ok":
            failed = True
            detail = f"no ok for: {line} (got {kind} {resp})"
            ok = False
        lr = LineResult(line=line, responses=list(resp), ok=ok, detail="" if ok else detail)
        results.append(lr)
        if failed:
            break
    return CaseResult(name=name, kind="pass", passed=not failed, detail=detail, lines=results)


def run_fail_script(client: GrblTcpClient, path: Path) -> CaseResult:
    """
    JSON schema:
    {
      "name": "optional",
      "setup": ["$X", "G21"],          # optional, expect ok
      "steps": [
        {"send": "G1 X1", "expect": "error", "code": "22"},
        {"send": "G999", "expect": "error"},
        {"send": "?", "expect": "status"}
      ]
    }
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("name") or path.stem
    results: List[LineResult] = []
    client.soft_reset()
    client.unlock_if_needed()
    for s in data.get("setup") or []:
        client.send_line(str(s), wait=1.0)

    failed = False
    detail = ""
    for step in data.get("steps") or []:
        send = str(step["send"])
        expect = str(step.get("expect", "error")).lower()
        code = step.get("code")
        codes = step.get("codes")
        allowed: Optional[List[str]] = None
        if codes is not None:
            allowed = [str(c) for c in codes]
        elif code is not None:
            allowed = [str(code)]
        resp = client.send_line(send, wait=float(step.get("wait", 2.0)))
        kind, got_code = classify_responses(resp)
        ok = False
        if expect == "error":
            ok = kind == "error" and (allowed is None or got_code in allowed)
        elif expect == "alarm":
            ok = kind == "alarm" and (allowed is None or got_code in allowed)
        elif expect == "ok":
            ok = kind == "ok"
        elif expect == "status":
            ok = kind in ("status", "ok")
        else:
            ok = False
            detail = f"unknown expect={expect}"
        if not ok and not detail:
            want = f"{expect}:{allowed}" if allowed else expect
            detail = f"step {send!r}: want {want}, got {kind}:{got_code} resp={resp}"
        results.append(
            LineResult(line=send, responses=list(resp), ok=ok, detail="" if ok else detail)
        )
        if not ok:
            failed = True
            break
    return CaseResult(name=name, kind="fail", passed=not failed, detail=detail, lines=results)


def run_validator(path: Path, validator: Path) -> Tuple[bool, str]:
    """
    Feed file contents on stdin. Some Windows builds hang when given a path
    argument alone; stdin is the reliable path for grblHAL_validator.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        proc = subprocess.run(
            [str(validator)],
            input=text,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return False, "validator not found"
    except subprocess.TimeoutExpired:
        return False, "validator timeout"
    out = (proc.stdout or "") + (proc.stderr or "")
    # Return code: 0 success, else line number of first error (upstream help).
    ok = proc.returncode == 0 and not ERROR_RE.search(out)
    return ok, (out.strip()[:2000] or f"exit={proc.returncode}")


def collect_pass_files() -> List[Path]:
    if not PASS_DIR.is_dir():
        return []
    return sorted(PASS_DIR.glob("*.nc"))


def collect_fail_files() -> List[Path]:
    if not FAIL_DIR.is_dir():
        return []
    return sorted(FAIL_DIR.glob("*.json"))


def print_report(cases: Sequence[CaseResult]) -> int:
    hard = [c for c in cases if c.kind != "soft"]
    soft = [c for c in cases if c.kind == "soft"]
    failed = [c for c in hard if not c.passed]
    print("")
    print("=== sim_regression report ===")
    for c in cases:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] ({c.kind}) {c.name}" + (f" — {c.detail}" if c.detail and not c.passed else ""))
    print(f"hard: {len(hard) - len(failed)}/{len(hard)} passed; soft: {len(soft)}")
    if failed:
        print("FAILED cases:")
        for c in failed:
            print(f"  - {c.name}: {c.detail}")
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grbl protocol regression via grblHAL sim TCP")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--validator-only",
        action="store_true",
        help="Only run grblHAL_validator on pass/*.nc (no TCP)",
    )
    ap.add_argument(
        "--include-repo-tests",
        action="store_true",
        help="Also stream a few Grbl_Esp32/src/tests/*.nc as soft checks",
    )
    ap.add_argument(
        "--start-sim",
        action="store_true",
        help="Spawn GRBLHAL_SIM -p PORT in background for this run",
    )
    ap.add_argument(
        "--with-validator",
        action="store_true",
        help="Also run grblHAL_validator on pass/*.nc after TCP cases",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases: List[CaseResult] = []
    sim_proc: Optional[subprocess.Popen] = None

    validator = find_validator()
    if args.validator_only:
        if not validator:
            print(
                "ERROR: grblHAL_validator not found. Set GRBLHAL_VALIDATOR or install from Web Builder.",
                file=sys.stderr,
            )
            print("  https://svn.io-engineering.com:8443/?driver=Simulator", file=sys.stderr)
            return 2
        for nc in collect_pass_files():
            ok, out = run_validator(nc, validator)
            cases.append(
                CaseResult(
                    name=f"validator:{nc.name}",
                    kind="pass",
                    passed=ok,
                    detail="" if ok else out[:300],
                )
            )
        code = print_report(cases)
        (RESULTS_DIR / "last_report.json").write_text(
            json.dumps([asdict(c) for c in cases], indent=2), encoding="utf-8"
        )
        return code

    if args.start_sim:
        sim = find_sim()
        if not sim:
            print(
                "ERROR: grblHAL_sim not found. Set GRBLHAL_SIM or install from Web Builder.",
                file=sys.stderr,
            )
            return 2
        # -n: no comment prefixes; -t 0: as fast as possible (official sim flag)
        sim_proc = subprocess.Popen(
            [str(sim), "-n", "-t", "0", "-p", str(args.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.2)

    client = GrblTcpClient(args.host, args.port, timeout=args.timeout)
    try:
        try:
            client.connect()
        except OSError as exc:
            print(
                f"ERROR: cannot connect to {args.host}:{args.port} ({exc}).\n"
                f"Start sim first, e.g. grblHAL_sim -p {args.port}\n"
                f"Web Builder: https://svn.io-engineering.com:8443/?driver=Simulator",
                file=sys.stderr,
            )
            return 2

        for nc in collect_pass_files():
            print(f"running pass: {nc.name} ...")
            cases.append(run_pass_file(client, nc))

        for js in collect_fail_files():
            print(f"running fail: {js.name} ...")
            cases.append(run_fail_script(client, js))

        if args.include_repo_tests and REPO_TESTS.is_dir():
            for name in ("parsetest.nc", "user_io.nc"):
                p = REPO_TESTS / name
                if p.is_file():
                    print(f"soft repo test: {name} ...")
                    cr = run_pass_file(client, p)
                    cr.kind = "soft"
                    # soft: never fail the suite alone
                    cases.append(cr)

        # Optional offline validator (can hang on some Windows path-arg builds)
        if args.with_validator and validator:
            for nc in collect_pass_files():
                ok, out = run_validator(nc, validator)
                cases.append(
                    CaseResult(
                        name=f"validator:{nc.name}",
                        kind="pass",
                        passed=ok,
                        detail="" if ok else out[:300],
                    )
                )
    finally:
        client.close()
        if sim_proc is not None:
            sim_proc.terminate()
            try:
                sim_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                sim_proc.kill()

    code = print_report(cases)
    report_path = RESULTS_DIR / "last_report.json"
    report_path.write_text(json.dumps([asdict(c) for c in cases], indent=2), encoding="utf-8")
    print(f"wrote {report_path}")
    return code


if __name__ == "__main__":
    sys.exit(main())
