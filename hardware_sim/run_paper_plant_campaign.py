#!/usr/bin/env python3
"""Run deterministic paper transport fault campaigns and emit coverage evidence."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from paper_plant import FaultProfile, PaperPlantConfig, simulate

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

CAMPAIGN = [
    (FaultProfile(name="nominal"), "completed", "paper_positioned"),
    (FaultProfile(name="slip_40pct", speed_scale=0.6), "completed", "paper_positioned"),
    (FaultProfile(name="jam", jam_at_mm=25.0), "failed", "timeout"),
    (FaultProfile(name="no_paper", paper_present=False), "failed", "timeout"),
    (FaultProfile(name="sensor_stuck_inactive", sensor_stuck=False), "failed", "timeout"),
    (FaultProfile(name="sensor_stuck_active", sensor_stuck=True), "failed", "sensor_active_too_early"),
    (FaultProfile(name="sensor_bounce", sensor_bounce_samples=8), "completed", "paper_positioned"),
    (FaultProfile(name="motor_reverse", reverse=True), "failed", "reverse_motion"),
    (FaultProfile(name="slip_plus_bounce", speed_scale=0.6, sensor_bounce_samples=8), "completed", "paper_positioned"),
    (FaultProfile(name="slip_plus_jam", speed_scale=0.6, jam_at_mm=25.0), "failed", "timeout"),
]

REQUIRED_COVERAGE = {
    "motor_start",
    "motor_stop",
    "sensor_debounce",
    "sensor_plausibility",
    "sensor_bounce",
    "sensor_stuck",
    "paper_slip",
    "motor_jam",
    "motor_reverse",
    "reverse_bound_check",
    "timeout",
    "overtravel_complete",
}


def run_campaign(names: Optional[set[str]] = None) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    aggregate_coverage: set[str] = set()
    for fault, expected_outcome, expected_reason in CAMPAIGN:
        if names is not None and fault.name not in names:
            continue
        result = simulate(PaperPlantConfig(), fault)
        aggregate_coverage.update(result["covered"])
        passed = result["outcome"] == expected_outcome and result["reason"] == expected_reason
        cases.append(
            {
                **result,
                "expected_outcome": expected_outcome,
                "expected_reason": expected_reason,
                "passed": passed,
            }
        )
    required = REQUIRED_COVERAGE if names is None else set()
    missing = sorted(required - aggregate_coverage)
    return {
        "suite": "paper_plant_fault_campaign",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if cases and all(case["passed"] for case in cases) and not missing else "fail",
        "virtual_time": True,
        "cases": cases,
        "coverage": {
            "covered": sorted(aggregate_coverage),
            "required": sorted(required),
            "missing": missing,
            "ratio": round(len(aggregate_coverage & required) / len(required), 4) if required else None,
        },
        "evidence_boundary": "deterministic mechanical/sensor model; not ESP32 scheduling, real motor torque, paper friction, Bluetooth transport, or HIL",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="deterministic paper plant fault campaign")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    allowed = {fault.name for fault, _, _ in CAMPAIGN}
    selected = set(args.only) if args.only else None
    unknown = sorted((selected or set()) - allowed)
    if unknown:
        parser.error(f"unknown fault profiles: {', '.join(unknown)}")
    report = run_campaign(selected)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = args.json_out or RESULTS / "paper_plant_campaign.json"
    if not path.is_absolute():
        path = HERE.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
