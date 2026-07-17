#!/usr/bin/env python3
"""Exhaustive bounded interaction campaign for the deterministic paper plant."""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from paper_plant import FaultProfile, PaperPlantConfig, simulate


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
FACTOR_VALUES: Dict[str, Tuple[str, ...]] = {
    "paper": ("present", "missing"),
    "speed": ("normal", "slip_40pct"),
    "drive": ("normal", "jam", "reverse"),
    "sensor": ("normal", "bounce", "stuck_inactive", "stuck_active"),
}
EXPECTED_REASONS = {"paper_positioned", "timeout", "reverse_motion", "sensor_active_too_early"}


def configurations() -> Iterable[Dict[str, str]]:
    names = tuple(FACTOR_VALUES)
    for values in itertools.product(*(FACTOR_VALUES[name] for name in names)):
        yield dict(zip(names, values))


def fault_from_config(config: Mapping[str, str]) -> FaultProfile:
    drive = config["drive"]
    sensor = config["sensor"]
    return FaultProfile(
        name="interaction:" + ",".join(f"{name}={config[name]}" for name in FACTOR_VALUES),
        paper_present=config["paper"] == "present",
        speed_scale=0.6 if config["speed"] == "slip_40pct" else 1.0,
        jam_at_mm=25.0 if drive == "jam" else None,
        sensor_stuck=False if sensor == "stuck_inactive" else True if sensor == "stuck_active" else None,
        sensor_bounce_samples=8 if sensor == "bounce" else 0,
        reverse=drive == "reverse",
    )


def stable_projection(result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "virtual_duration_ms": result.get("virtual_duration_ms"),
        "final_position_mm": result.get("final_position_mm"),
        "terminal_motor_on": result.get("terminal_motor_on"),
        "covered": result.get("covered"),
        "transitions": result.get("transitions"),
    }


def property_violations(config: Mapping[str, str], result: Mapping[str, Any], rerun: Mapping[str, Any]) -> List[str]:
    violations: List[str] = []
    outcome = result.get("outcome")
    reason = result.get("reason")
    if stable_projection(result) != stable_projection(rerun):
        violations.append("nondeterministic_replay")
    if outcome not in {"completed", "failed"}:
        violations.append("non_terminal_outcome")
    if reason not in EXPECTED_REASONS:
        violations.append("unknown_terminal_reason")
    if result.get("terminal_motor_on") is not False or "motor_stop" not in result.get("covered", []):
        violations.append("motor_not_stopped")
    transitions = result.get("transitions", [])
    if not transitions or transitions[-1].get("event") != "finish":
        violations.append("missing_finish_transition")
    safe_completion = (
        config["paper"] == "present"
        and config["drive"] == "normal"
        and config["sensor"] in {"normal", "bounce"}
    )
    if (outcome == "completed") != safe_completion:
        violations.append("unsafe_or_missing_completion")
    return violations


def pairwise_coverage(configs: Sequence[Mapping[str, str]]) -> Dict[str, Any]:
    names = tuple(FACTOR_VALUES)
    expected = {
        (left, left_value, right, right_value)
        for left_index, left in enumerate(names)
        for right in names[left_index + 1 :]
        for left_value in FACTOR_VALUES[left]
        for right_value in FACTOR_VALUES[right]
    }
    covered = {
        (left, config[left], right, config[right])
        for config in configs
        for left_index, left in enumerate(names)
        for right in names[left_index + 1 :]
    }
    missing = sorted(expected - covered)
    return {
        "strength": 2,
        "covered": len(covered),
        "required": len(expected),
        "missing": [list(item) for item in missing],
        "ratio": round(len(covered) / len(expected), 4) if expected else 1.0,
    }


def failure_weight(config: Mapping[str, str]) -> Tuple[int, Tuple[str, ...]]:
    defaults = {"paper": "present", "speed": "normal", "drive": "normal", "sensor": "normal"}
    values = tuple(config[name] for name in FACTOR_VALUES)
    return sum(config[name] != defaults[name] for name in FACTOR_VALUES), values


def run_interactions() -> Dict[str, Any]:
    plant_config = PaperPlantConfig()
    cases: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    tested_configs = list(configurations())
    for config in tested_configs:
        first = simulate(plant_config, fault_from_config(config))
        second = simulate(plant_config, fault_from_config(config))
        violations = property_violations(config, first, second)
        case = {
            "config": config,
            "outcome": first["outcome"],
            "reason": first["reason"],
            "virtual_duration_ms": first["virtual_duration_ms"],
            "violations": violations,
        }
        cases.append(case)
        if violations:
            failures.append(case)
    interactions = pairwise_coverage(tested_configs)
    failures.sort(key=lambda item: failure_weight(item["config"]))
    outcomes = Counter(case["outcome"] for case in cases)
    reasons = Counter(case["reason"] for case in cases)
    return {
        "suite": "paper_plant_interaction_campaign",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not failures and not interactions["missing"] else "fail",
        "virtual_time": True,
        "deterministic_replays": 2,
        "factor_values": FACTOR_VALUES,
        "configuration_count": len(cases),
        "summary": {"outcomes": dict(sorted(outcomes.items())), "reasons": dict(sorted(reasons.items()))},
        "interaction_coverage": interactions,
        "failures": failures,
        "minimal_failure": failures[0] if failures else None,
        "cases": cases,
        "evidence_boundary": "bounded deterministic mechanical/sensor interactions; not ESP32 scheduling, motor torque, paper friction distribution, Bluetooth transport, or HIL",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="bounded paper plant interaction campaign")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_interactions()
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = args.json_out or RESULTS / "paper_plant_interactions.json"
    if not path.is_absolute():
        path = HERE.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
