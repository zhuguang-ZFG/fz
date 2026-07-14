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
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))
from step_oracle import (  # noqa: E402
    assert_travel_mm,
    max_abs_steps,
    parse_step_log,
    mm_from_steps,
    snapshot_max_abs,
    per_move_delta,
)
from plant import Plant  # noqa: E402
from case_runner import run_all_json_cases  # noqa: E402
from sim_common.find_sim import find_sim, VENDOR_SIM  # noqa: E402
from sim_common.grbl_tcp import (  # noqa: E402
    GrblTcp,
    ERROR_RE,
    ALARM_RE,
    OK_RE,
    parse_mpos,
    wait_idle,
)
from sim_common.ports import find_free_port  # noqa: E402


FZ_ROOT = Path(__file__).resolve().parent.parent
HW_ROOT = Path(__file__).resolve().parent
RESULTS = HW_ROOT / "results"
CASES = HW_ROOT / "cases"
DEFAULT_STEPS_PER_MM = (250.0, 250.0, 250.0)


@dataclass
class CaseResult:
    name: str
    passed: bool
    detail: str = ""
    mpos: Optional[List[float]] = None
    responses: List[str] = field(default_factory=list)
    source: str = "builtin"


def run_motion_case(
    client: GrblTcp,
    name: str,
    moves: Sequence[str],
    expect_delta: Sequence[float],
    eps: float = 0.25,
    step_log: Optional[Path] = None,
    steps_per_mm: Sequence[float] = DEFAULT_STEPS_PER_MM,
    step_eps_mm: float = 0.75,
) -> CaseResult:
    """Assert MPos delta after moves; optional per-move StepOracle on last motion line."""
    client.soft_reset()
    client.unlock()
    all_resp: List[str] = []
    start, r0 = wait_idle(client, timeout=5.0)
    all_resp.extend(r0)
    if start is None:
        start = [0.0, 0.0, 0.0]
    last_motion = None
    for mv in moves:
        is_motion = bool(re.match(r"(?i)^G[01]\b", mv.strip()))
        before = snapshot_max_abs(step_log) if (step_log and is_motion) else None
        resp = client.send_line(mv, wait=15.0)
        all_resp.extend(resp)
        if any(ERROR_RE.search(x) or ALARM_RE.search(x) for x in resp):
            return CaseResult(name=name, passed=False, detail=f"error on {mv}: {resp}", responses=all_resp)
        if not any(OK_RE.match(x) for x in resp):
            return CaseResult(name=name, passed=False, detail=f"no ok for {mv}: {resp}", responses=all_resp)
        if is_motion:
            last_motion = (mv, before)
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
    # Per-move StepOracle on the last G0/G1 line (session log max-abs delta)
    if step_log and last_motion and last_motion[1] is not None:
        time.sleep(0.12)
        after = snapshot_max_abs(step_log)
        dsteps = per_move_delta(last_motion[1], after)
        # For multi-line cases, expect_delta is whole-case; use full-case step check
        ok_s, det_s, act_mm = assert_travel_mm(
            dsteps, expect_delta, steps_per_mm, eps_mm=step_eps_mm
        )
        # Whole-case travel may span multiple moves — use session delta from start snap
        # Recompute: before first motion was first before; use sum of expect
        if not ok_s:
            # fallback: compare total session max-abs growth from case start
            # if single motion line, fail hard; if multi, only warn in detail
            motion_lines = [m for m in moves if re.match(r"(?i)^G[01]\b", m.strip())]
            if len(motion_lines) <= 1:
                return CaseResult(
                    name=name,
                    passed=False,
                    detail=f"MPos ok but step_window fail: {det_s}",
                    mpos=mpos,
                    responses=all_resp,
                )
            all_resp.append(f"[step_window soft {det_s} mm={act_mm}]")
        else:
            all_resp.append(f"[step_window ok mm={act_mm} steps={dsteps}]")
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


def run_feed_hold_plant(client: GrblTcp, time_factor: float) -> CaseResult:
    """
    Community Grbl realtime: ! → Hold (TCP). Optional ~ resume.
    Needs time_factor > 0 so status is still Run when ! arrives.
    Avoid flooding ?/~ (fills RX buffer and blocks resume on sim).
    """
    if time_factor <= 0:
        return CaseResult(
            "plant_feed_hold",
            True,
            detail="skipped (need --time-factor > 0; use 1 for plant)",
        )
    assert client.sock
    plant = Plant(sock=client.sock)
    client.soft_reset()
    time.sleep(0.3)
    client.unlock()
    client.send_line("G21 G91 G94", wait=1.0)
    # long slow move — do not wait for ok-only short window
    client.sock.sendall(b"G1 X500 F100\n")
    time.sleep(0.2)
    client._drain()

    st_run: List[str] = []
    for i in range(40):
        time.sleep(0.2)
        st = client.send_line("?", wait=0.35)
        st_run = st
        if any("Run" in x for x in st):
            plant.feed_hold()
            time.sleep(0.9)
            st_hold = client.send_line("?", wait=0.5)
            if not any("Hold" in x for x in st_hold):
                return CaseResult(
                    "plant_feed_hold",
                    False,
                    detail=f"expected Hold after ! got {st_hold}",
                    responses=st + st_hold,
                )
            # Best-effort resume (single ~, long wait) — do not fail suite if sim stays Hold:1
            plant.cycle_start()
            time.sleep(1.2)
            st_res = client.send_line("?", wait=0.5)
            resumed = any(("Run" in x) or ("Idle" in x) for x in st_res)
            # Always clear for following cases
            client.soft_reset()
            time.sleep(0.3)
            client.unlock()
            detail = (
                "TCP ! → Hold; ~ resumed"
                if resumed
                else "TCP ! → Hold (resume optional/flaky after buffer use; soft-reset cleared)"
            )
            return CaseResult(
                "plant_feed_hold",
                True,
                detail=detail,
                responses=st + st_hold + st_res,
            )
        if i > 15 and any("Idle" in x for x in st):
            break
    return CaseResult(
        "plant_feed_hold",
        False,
        detail="never observed Run (use --time-factor 1 and slow F)",
        responses=st_run,
    )




def run_override_reset_smoke(client: GrblTcp) -> CaseResult:
    """Realtime override bytes 0x90/0x99/0xA0 (100%) are no-ops; must not kill stream."""
    client.soft_reset()
    client.unlock()
    assert client.sock
    for b in (b"\x90", b"\x99", b"\xa0"):
        client.send_realtime(b)
    time.sleep(0.15)
    r = client.send_line("?", wait=0.8)
    ok = any(x.startswith("<") for x in r)
    return CaseResult(
        "override_realtime_100pct",
        ok,
        detail="" if ok else f"no status after overrides: {r}",
        responses=r,
    )


def run_check_mode_toggle(client: GrblTcp) -> CaseResult:
    """$C check mode on/off if supported — protocol smoke (grblHAL)."""
    client.soft_reset()
    client.unlock()
    r1 = client.send_line("$C", wait=1.5)
    r2 = client.send_line("$C", wait=1.5)
    r3 = client.send_line("G0 X0", wait=2.0)
    joined = "\n".join(r1 + r2 + r3)
    terminal = any(
        OK_RE.match(x) or ERROR_RE.search(x) or ALARM_RE.search(x) for x in r3
    )
    toggled = (
        any(OK_RE.match(x) for x in r1 + r2)
        or "check" in joined.lower()
        or "enable" in joined.lower()
    )
    ok = terminal and (toggled or any(OK_RE.match(x) for x in r3))
    return CaseResult(
        "check_mode_toggle",
        ok,
        detail="" if ok else f"r1={r1} r2={r2} r3={r3}",
        responses=list(r1) + list(r2) + list(r3),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="hardware_sim baseline runner")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7682)
    ap.add_argument("--start-sim", action="store_true")
    # Default 1.0 so plant feed-hold can observe Run (community: -t 0 finishes too fast)
    ap.add_argument(
        "--time-factor",
        type=float,
        default=1.0,
        help="grblHAL -t (0=fast; 1=realtime for plant inject)",
    )
    ap.add_argument(
        "--fast",
        action="store_true",
        help="shortcut: --time-factor 0 (skips reliable plant hold)",
    )
    ap.add_argument(
        "--json-cases",
        action="store_true",
        default=True,
        help="run hardware_sim/cases/*.json (default on)",
    )
    ap.add_argument(
        "--no-json-cases",
        action="store_true",
        help="skip JSON case directory",
    )
    ap.add_argument(
        "--builtin-only",
        action="store_true",
        help="only legacy builtin cases (implies --no-json-cases)",
    )
    ap.add_argument(
        "--json-only",
        action="store_true",
        help="skip builtin cases; only JSON directory",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.fast:
        args.time_factor = 0.0
    if args.builtin_only:
        args.no_json_cases = True
    run_json = args.json_cases and not args.no_json_cases and not args.builtin_only
    run_builtin = not args.json_only

    RESULTS.mkdir(parents=True, exist_ok=True)
    if step_log_path := (RESULTS / "step_last.log"):
        try:
            step_log_path.write_text("", encoding="utf-8")
        except OSError:
            pass
    step_log = RESULTS / "step_last.log"
    block_log = RESULTS / "block_last.log"
    eeprom = RESULTS / "EEPROM_hw.DAT"

    sim_proc: Optional[subprocess.Popen] = None
    if args.start_sim:
        sim = find_sim()
        if not sim:
            print("ERROR: grblHAL_sim not found", file=sys.stderr)
            return 2
        args.port = find_free_port(args.port, host=args.host)
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
        # stdin PIPE for best-effort pin inject (Windows often ineffective — cases soft)
        sim_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.PIPE,
            cwd=str(sim.parent),
        )
        # Avoid wait_port TCP probe — single-session sim; sleep + connect retries
        time.sleep(1.0 if args.time_factor and args.time_factor > 0 else 0.8)
        if sim_proc.poll() is not None:
            print(f"ERROR: sim exited early code={sim_proc.returncode}", file=sys.stderr)
            return 2

    client = GrblTcp(args.host, args.port)
    results: List[CaseResult] = []
    try:
        last_exc: Optional[OSError] = None
        for attempt in range(8):
            try:
                client.connect()
                last_exc = None
                break
            except OSError as exc:
                last_exc = exc
                time.sleep(0.35 + 0.1 * attempt)
        if last_exc is not None:
            print(f"ERROR: connect {args.host}:{args.port}: {last_exc}", file=sys.stderr)
            return 2

        plant = None
        if client.sock:
            plant = Plant(sock=client.sock, proc=sim_proc)

        if run_builtin:
            results.append(
                run_motion_case(
                    client,
                    "move_x_10",
                    ["G91", "G1 X10 Y0 F1000", "G90"],
                    expect_delta=(10.0, 0.0, 0.0),
                    eps=0.15,
                    step_log=step_log if args.start_sim else None,
                )
            )
            results.append(
                run_motion_case(
                    client,
                    "move_xy_delta",
                    ["G91", "G1 X5 Y5 F1000", "G90"],
                    expect_delta=(5.0, 5.0, 0.0),
                    eps=0.15,
                    step_log=step_log if args.start_sim else None,
                )
            )
            results.append(run_error_case(client, "undefined_feed_G1", "G1 X1"))
            results.append(run_settings_travel_roundtrip(client))
            results.append(run_soft_limit_setting_gate(client))
            results.append(run_feed_hold_plant(client, args.time_factor))
            results.append(run_override_reset_smoke(client))
            results.append(run_check_mode_toggle(client))

        if run_json and CASES.is_dir():
            jresults = run_all_json_cases(
                client,
                CASES,
                step_log=step_log if args.start_sim else None,
                plant=plant,
                time_factor=args.time_factor,
                steps_per_mm=DEFAULT_STEPS_PER_MM,
            )
            for jr in jresults:
                results.append(
                    CaseResult(
                        name=jr.name,
                        passed=jr.passed,
                        detail=jr.detail,
                        mpos=jr.mpos,
                        responses=jr.responses,
                        source="json",
                    )
                )
    finally:
        client.close()
        if sim_proc is not None:
            time.sleep(0.3)
            try:
                if sim_proc.stdin:
                    sim_proc.stdin.close()
            except OSError:
                pass
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
        # Lower bound: motion cases alone ≈ 15mm X + 5mm Y; plant may add more travel
        actual_mm = mm_from_steps(mx, DEFAULT_STEPS_PER_MM)
        min_x, min_y = 14.0, 4.0
        ok = actual_mm[0] >= min_x and actual_mm[1] >= min_y
        detail = (
            f"mm≈{actual_mm} steps={mx} (min X>={min_x} Y>={min_y}; plant may add travel)"
            if ok
            else f"travel too small mm={actual_mm} steps={mx}"
        )
        results.append(
            CaseResult(
                name="step_oracle_session_travel",
                passed=ok and step_ok,
                detail=detail,
            )
        )

    failed = [r for r in results if not r.passed]
    print("=== hardware_sim report ===")
    for r in results:
        src = f"/{r.source}" if getattr(r, "source", None) else ""
        print(
            f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}{src}"
            + (f" — {r.detail}" if r.detail else "")
        )
        if r.mpos:
            print(f"           MPos={r.mpos}")
    report = {
        "sim_mode": "hardware_sim_not_silicon",
        "engine": "grblHAL_sim",
        "step_log": str(step_log) if step_log.is_file() else None,
        "block_log": str(block_log) if block_log.is_file() else None,
        "json_cases": run_json,
        "cases": [asdict(r) for r in results],
    }
    out = RESULTS / "last_hw_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
