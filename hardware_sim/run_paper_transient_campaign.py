#!/usr/bin/env python3
"""Deterministic virtual-time transient fault campaign with window shrinking."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from paper_plant import FaultProfile, PaperPlantConfig, TransientFault, simulate


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SCENARIOS: Tuple[Tuple[str, Tuple[TransientFault, ...], str, str, Optional[str]], ...] = (
    ("brief_jam_recovers", (TransientFault("jam", 300, 500),), "completed", "paper_positioned", None),
    ("persistent_jam_times_out", (TransientFault("jam", 300, 2400),), "failed", "timeout", "jam"),
    ("sensor_dropout_recovers", (TransientFault("sensor", 750, 1000, 0.0),), "completed", "paper_positioned", None),
    ("early_false_active_fails", (TransientFault("sensor", 0, 100, 1.0),), "failed", "sensor_active_too_early", "sensor"),
    ("speed_dip_recovers", (TransientFault("speed_scale", 200, 900, 0.25),), "completed", "paper_positioned", None),
    (
        "jam_and_dropout_recover",
        (TransientFault("jam", 300, 650), TransientFault("sensor", 650, 950, 0.0)),
        "completed",
        "paper_positioned",
        None,
    ),
)


def stable_projection(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "outcome": result["outcome"],
        "reason": result["reason"],
        "virtual_duration_ms": result["virtual_duration_ms"],
        "final_position_mm": result["final_position_mm"],
        "terminal_motor_on": result["terminal_motor_on"],
        "covered": result["covered"],
        "transitions": result["transitions"],
    }


def shrink_window(
    transient: TransientFault,
    tick_ms: int,
    preserves_failure: Callable[[TransientFault], bool],
) -> TransientFault:
    current = transient
    while current.start_ms + tick_ms < current.end_ms:
        candidate = replace(current, start_ms=current.start_ms + tick_ms)
        if not preserves_failure(candidate):
            break
        current = candidate
    while current.end_ms - tick_ms > current.start_ms:
        candidate = replace(current, end_ms=current.end_ms - tick_ms)
        if not preserves_failure(candidate):
            break
        current = candidate
    return current


def fault_dict(transient: TransientFault) -> Dict[str, Any]:
    return {"kind": transient.kind, "start_ms": transient.start_ms, "end_ms": transient.end_ms, "value": transient.value}


def run_campaign() -> Dict[str, Any]:
    config = PaperPlantConfig()
    cases: List[Dict[str, Any]] = []
    for name, transients, expected_outcome, expected_reason, shrink_kind in SCENARIOS:
        first = simulate(config, FaultProfile(name=name), transients)
        second = simulate(config, FaultProfile(name=name), transients)
        violations: List[str] = []
        if stable_projection(first) != stable_projection(second):
            violations.append("nondeterministic_replay")
        if first["outcome"] != expected_outcome or first["reason"] != expected_reason:
            violations.append("unexpected_terminal_result")
        if first["terminal_motor_on"] is not False or "motor_stop" not in first["covered"]:
            violations.append("motor_not_stopped")
        starts = [item for item in first["transitions"] if item["event"] == "fault_start"]
        if not starts:
            violations.append("fault_window_not_observed")
        minimal_failure_window = None
        if shrink_kind is not None and first["outcome"] == "failed":
            shrink_index = next(index for index, item in enumerate(transients) if item.kind == shrink_kind)

            def preserves(candidate: TransientFault) -> bool:
                candidate_windows = list(transients)
                candidate_windows[shrink_index] = candidate
                result = simulate(config, FaultProfile(name=name), candidate_windows)
                return result["outcome"] == first["outcome"] and result["reason"] == first["reason"]

            minimal = shrink_window(transients[shrink_index], config.tick_ms, preserves)
            minimal_failure_window = fault_dict(minimal)
            if not preserves(minimal):
                violations.append("invalid_minimal_failure_window")
            shorter = replace(minimal, end_ms=minimal.end_ms - config.tick_ms) if minimal.end_ms - config.tick_ms > minimal.start_ms else None
            later = replace(minimal, start_ms=minimal.start_ms + config.tick_ms) if minimal.start_ms + config.tick_ms < minimal.end_ms else None
            if (shorter is not None and preserves(shorter)) or (later is not None and preserves(later)):
                violations.append("failure_window_not_locally_minimal")
        cases.append(
            {
                "name": name,
                "windows": [fault_dict(item) for item in transients],
                "outcome": first["outcome"],
                "reason": first["reason"],
                "virtual_duration_ms": first["virtual_duration_ms"],
                "minimal_failure_window": minimal_failure_window,
                "violations": violations,
                "passed": not violations,
            }
        )
    return {
        "suite": "paper_plant_transient_campaign",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(case["passed"] for case in cases) else "fail",
        "virtual_time": True,
        "window_semantics": "start_ms inclusive, end_ms exclusive; applied before each virtual tick",
        "cases": cases,
        "evidence_boundary": "deterministic scheduled mechanical/sensor faults; not ESP32 task scheduling, interrupt latency, electrical transients, Bluetooth transport, or HIL",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="paper plant transient fault campaign")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_campaign()
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = args.json_out or RESULTS / "paper_plant_transients.json"
    if not path.is_absolute():
        path = HERE.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
