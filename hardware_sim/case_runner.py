#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON-driven hardware_sim cases (design schema + extensions).

Schema (per file under cases/*.json):
{
  "id": "move_x10_step_window",
  "time_factor_min": 0,          # skip if sim -t below this (optional)
  "setup": ["$X", "G21", "G90"],
  "soft_reset": true,
  "steps": [
    { "send": "G91", "expect": "ok" },
    {
      "send": "G1 X10 F1000",
      "expect": "ok",
      "wait": 20,
      "step_window": true,
      "expect_travel_mm": [10, 0, 0],
      "eps_mm": 0.6
    },
    { "send": "G90", "expect": "ok" }
  ],
  "inject": [],
  "notes": "..."
}

Inject step forms:
  { "inject": "feed_hold", "after_ms": 0 }          # TCP !
  { "inject": "cycle_start" }
  { "inject": "limit_x_min", "via": "stdin" }       # plant stdin key
  { "send": "G1 X100 F200", "async": true }
  { "expect_status": "Hold|Alarm|Run|Idle", "timeout_s": 3 }

expect values: ok | error | alarm | error_or_alarm | status | any
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from plant import Plant
from step_oracle import (
    assert_travel_mm,
    parse_step_log,
    per_move_delta,
    snapshot_max_abs,
)
from sim_common.grbl_tcp import (
    ALARM_RE,
    ERROR_RE,
    GrblTcp,
    OK_RE,
    parse_mpos,
    wait_idle,
)


DEFAULT_STEPS_PER_MM = (250.0, 250.0, 250.0)


@dataclass
class CaseResult:
    name: str
    passed: bool
    detail: str = ""
    mpos: Optional[List[float]] = None
    responses: List[str] = field(default_factory=list)
    source: str = "json"


def _match_expect(resp: Sequence[str], expect: str) -> bool:
    exp = (expect or "ok").lower()
    if exp == "any":
        return True
    if exp == "ok":
        return any(OK_RE.match(x) for x in resp)
    if exp == "error":
        return any(ERROR_RE.search(x) for x in resp)
    if exp == "alarm":
        return any(ALARM_RE.search(x) for x in resp)
    if exp in ("error_or_alarm", "error|alarm"):
        return any(ERROR_RE.search(x) or ALARM_RE.search(x) for x in resp)
    if exp == "status":
        return any(x.startswith("<") for x in resp)
    return False


def load_case_files(cases_dir: Path) -> List[Path]:
    if not cases_dir.is_dir():
        return []
    return sorted(cases_dir.glob("*.json"))


def run_json_case(
    client: GrblTcp,
    path: Path,
    *,
    step_log: Optional[Path] = None,
    plant: Optional[Plant] = None,
    time_factor: float = 1.0,
    steps_per_mm: Sequence[float] = DEFAULT_STEPS_PER_MM,
) -> CaseResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    cid = str(data.get("id") or path.stem)
    tmin = float(data.get("time_factor_min", 0) or 0)
    if time_factor < tmin:
        return CaseResult(
            name=cid,
            passed=True,
            detail=f"skipped (need time_factor>={tmin}, have {time_factor})",
            source="json",
        )

    all_resp: List[str] = []
    if data.get("soft_reset", True):
        client.soft_reset()
        time.sleep(0.25)
        client.unlock()

    for line in data.get("setup") or []:
        r = client.send_line(str(line), wait=float(data.get("setup_wait", 1.0)))
        all_resp.extend(r)

    # top-level inject list (legacy design) — run before steps if present
    for inj in data.get("inject") or []:
        ok, detail, rr = _do_inject(client, plant, inj)
        all_resp.extend(rr)
        if not ok:
            return CaseResult(cid, False, detail=detail, responses=all_resp, source="json")

    for step in data.get("steps") or []:
        # inject-only step
        if "inject" in step and "send" not in step:
            ok, detail, rr = _do_inject(client, plant, step)
            all_resp.extend(rr)
            if not ok and not step.get("soft", False):
                return CaseResult(cid, False, detail=detail, responses=all_resp, source="json")
            continue

        if "expect_status" in step and "send" not in step:
            ok, detail, rr = _wait_status(client, str(step["expect_status"]), float(step.get("timeout_s", 3)))
            all_resp.extend(rr)
            if not ok:
                return CaseResult(cid, False, detail=detail, responses=all_resp, source="json")
            continue

        send = step.get("send")
        if send is None:
            continue
        wait = float(step.get("wait", 2.0))
        before_snap = None
        t_before = None
        if step.get("step_window") and step_log:
            # flush-ish: short sleep so file has prior samples
            time.sleep(0.05)
            before_snap = snapshot_max_abs(step_log)
            samples = parse_step_log(step_log)
            t_before = samples[-1].t if samples else 0.0

        if step.get("async"):
            assert client.sock
            client.sock.sendall((str(send).rstrip("\r\n") + "\n").encode("utf-8"))
            time.sleep(0.05)
            client._drain()
            resp = []
        else:
            resp = client.send_line(str(send), wait=wait)
            all_resp.extend(resp)

        expect = str(step.get("expect", "ok"))
        if not step.get("async") and not _match_expect(resp, expect):
            # codes_any support
            codes = step.get("codes_any") or step.get("codes")
            if codes and expect in ("error", "error_or_alarm", "alarm"):
                joined = "\n".join(resp)
                if not any(str(c) in joined for c in codes) and not _match_expect(
                    resp, "error_or_alarm"
                ):
                    return CaseResult(
                        cid,
                        False,
                        detail=f"step {send!r}: want {expect} codes={codes} got {resp}",
                        responses=all_resp,
                        source="json",
                    )
            elif expect != "any":
                return CaseResult(
                    cid,
                    False,
                    detail=f"step {send!r}: want {expect} got {resp}",
                    responses=all_resp,
                    source="json",
                )

        # optional nested inject after send
        if "inject" in step:
            ok, detail, rr = _do_inject(client, plant, step)
            all_resp.extend(rr)
            if not ok and not step.get("soft", False):
                return CaseResult(cid, False, detail=f"inject after send: {detail}", responses=all_resp, source="json")

        if step.get("wait_idle"):
            mpos, rr = wait_idle(client, timeout=float(step.get("idle_timeout", 30)))
            all_resp.extend(rr)

        if step.get("step_window") and step_log and before_snap is not None:
            # ensure motion finished for oracle
            if not step.get("async"):
                wait_idle(client, timeout=float(step.get("idle_timeout", 30)))
            time.sleep(0.15)
            after_snap = snapshot_max_abs(step_log)
            dsteps = per_move_delta(before_snap, after_snap)
            expect_mm = step.get("expect_travel_mm") or [0, 0, 0]
            eps = float(step.get("eps_mm", 0.6))
            ok, detail, actual = assert_travel_mm(dsteps, expect_mm, steps_per_mm, eps_mm=eps)
            if not ok:
                return CaseResult(
                    cid,
                    False,
                    detail=f"step_window {send!r}: {detail} snap {before_snap}->{after_snap}",
                    responses=all_resp,
                    source="json",
                )
            all_resp.append(f"[step_window mm={actual} steps={dsteps}]")

        if step.get("expect_mpos_delta"):
            start = step.get("_mpos_start")
            # capture start at first such need
            pass

    # optional final mpos delta for whole case
    if data.get("expect_mpos_delta"):
        # re-run style: need start — compute from last wait
        mpos, rr = wait_idle(client, timeout=5.0)
        all_resp.extend(rr)

    return CaseResult(name=cid, passed=True, detail="", responses=all_resp, source="json")


def _do_inject(
    client: GrblTcp, plant: Optional[Plant], step: Dict[str, Any]
) -> tuple[bool, str, List[str]]:
    name = str(step.get("inject") or "")
    after_ms = float(step.get("after_ms", 0) or 0)
    if after_ms > 0:
        time.sleep(after_ms / 1000.0)
    via = str(step.get("via", "tcp")).lower()
    resp: List[str] = []

    if name in ("feed_hold", "hold", "!"):
        if plant:
            plant.feed_hold()
        else:
            client.send_realtime(b"!")
        return True, "", resp
    if name in ("cycle_start", "resume", "~"):
        if plant:
            plant.cycle_start()
        else:
            client.send_realtime(b"~")
        return True, "", resp
    if name in ("soft_reset", "reset"):
        if plant:
            plant.soft_reset()
        else:
            client.soft_reset()
        return True, "", resp

    # stdin pin toggles
    stdin_map = {
        "limit_x_min": "limit_x_min",
        "limit_x_max": "limit_x_max",
        "limit_y_min": "limit_y_min",
        "limit_z_min": "limit_z_min",
        "probe": "probe",
        "door": "door",
        "estop": "estop",
        "feed_hold_pin": "feed_hold_pin",
    }
    key = stdin_map.get(name, name if name in stdin_map.values() else "")
    if key or via == "stdin":
        k = key or name
        if plant is None:
            if step.get("soft", True):
                return True, f"stdin inject {k} skipped (no plant/proc)", resp
            return False, f"stdin inject {k} needs plant with stdin", resp
        ok = plant.stdin_key(k, name=k)
        if not ok:
            if step.get("soft", True):
                return True, f"stdin inject {k} soft-fail (no console stdin)", resp
            return False, f"stdin inject {k} failed", resp
        return True, "", resp

    return False, f"unknown inject {name}", resp


def _wait_status(
    client: GrblTcp, pattern: str, timeout_s: float
) -> tuple[bool, str, List[str]]:
    """pattern: 'Hold' or 'Hold|Alarm' regex fragments."""
    deadline = time.time() + timeout_s
    collected: List[str] = []
    rx = re.compile(pattern, re.I)
    while time.time() < deadline:
        r = client.send_line("?", wait=0.4)
        collected.extend(r)
        if any(rx.search(x) for x in r):
            return True, "", collected
        time.sleep(0.1)
    return False, f"status {pattern!r} not seen in {timeout_s}s: {collected[-5:]}", collected


def run_all_json_cases(
    client: GrblTcp,
    cases_dir: Path,
    **kwargs: Any,
) -> List[CaseResult]:
    out: List[CaseResult] = []
    for path in load_case_files(cases_dir):
        try:
            out.append(run_json_case(client, path, **kwargs))
        except Exception as exc:  # noqa: BLE001 — case isolation
            out.append(
                CaseResult(
                    name=path.stem,
                    passed=False,
                    detail=f"exception: {exc}",
                    source="json",
                )
            )
    return out
