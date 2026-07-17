#!/usr/bin/env python3
"""Schema and delta-debugging helpers for native protocol scenarios."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
ALLOWED_EXPECT = {"motion_g0_g3", "motion_line", "defer_motion", "modal_before", "modal_after", "distance", "units", "feed_mode", "armed", "pending", "running", "supplied_matches", "expected_nonzero", "license_before", "license_after"}


def validate_scenario(data: Any, source: str = "scenario") -> List[str]:
    errors: List[str] = []
    if not isinstance(data, dict):
        return [f"{source}: root must be object"]
    if data.get("domain", "protocol") not in {"protocol", "license", "paper_bt_ack"}:
        errors.append(f"{source}: domain must be protocol, license, or paper_bt_ack")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append(f"{source}: name must be non-empty string")
    sequence_key = "events" if data.get("domain") == "paper_bt_ack" else "lines"
    if data.get("domain") == "license":
        if not isinstance(data.get("license"), dict):
            errors.append(f"{source}: license must be object")
    if not isinstance(data.get(sequence_key), list) or not data[sequence_key]:
        errors.append(f"{source}: lines must be non-empty list")
    else:
        for index, line in enumerate(data[sequence_key]):
            if not isinstance(line, str) or not line.strip():
                errors.append(f"{source}: lines[{index}] must be non-empty string")
    for key in ("paper_running", "modal_motion_active", "stateful_modal"):
        if key in data and not isinstance(data[key], bool):
            errors.append(f"{source}: {key} must be boolean")
    expected = data.get("expect", [])
    if not isinstance(expected, list):
        errors.append(f"{source}: expect must be list")
    else:
        if len(expected) != len(data.get(sequence_key, [])):
            errors.append(f"{source}: expect length must equal lines length")
        for index, item in enumerate(expected):
            if not isinstance(item, dict):
                errors.append(f"{source}: expect[{index}] must be object")
                continue
            for key, value in item.items():
                if key not in ALLOWED_EXPECT:
                    errors.append(f"{source}: expect[{index}] unknown field {key}")
                if key in {"distance", "units", "feed_mode"}:
                    if not isinstance(value, str):
                        errors.append(f"{source}: expect[{index}].{key} must be string")
                elif not isinstance(value, bool):
                    errors.append(f"{source}: expect[{index}].{key} must be boolean")
    return errors


def load_scenario(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_scenario(data, path.as_posix())
    if errors:
        raise ValueError("; ".join(errors))
    return data


def minimize_lines(lines: Sequence[str], fails: Callable[[Sequence[str]], bool]) -> List[str]:
    """Delta-debug a failing sequence while preserving the supplied predicate."""
    current = list(lines)
    granularity = 2
    while len(current) >= 2:
        chunk = max(1, (len(current) + granularity - 1) // granularity)
        reduced = False
        for start in range(0, len(current), chunk):
            candidate = current[:start] + current[start + chunk:]
            if candidate and fails(candidate):
                current = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if not reduced:
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)
    return current


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
