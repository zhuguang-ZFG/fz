#!/usr/bin/env python3
"""Validate reviewed paper-plant parameters against product firmware sources."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from paper_plant import PaperPlantConfig


HERE = Path(__file__).resolve().parent
FZ_ROOT = HERE.parent
RESULTS = HERE / "results"
DEFAULT_CONTRACT = HERE / "paper_firmware_contract.json"
DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+([^\s/]+)", re.MULTILINE)
INTEGER = re.compile(r"^(?:0[xX][0-9A-Fa-f]+|[0-9]+)[uUlL]*$")


def parse_numeric_defines(text: str) -> Dict[str, int]:
    values: Dict[str, int] = {}
    for name, token in DEFINE.findall(text):
        if not INTEGER.fullmatch(token):
            continue
        normalized = token.rstrip("uUlL")
        values[name] = int(normalized, 0)
    return values


def load_contract(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("paper firmware contract version must be 1")
    if not isinstance(data.get("firmware_constants"), dict) or not data["firmware_constants"]:
        raise ValueError("firmware_constants must be a non-empty object")
    if not isinstance(data.get("plant_abstractions"), dict) or not data["plant_abstractions"]:
        raise ValueError("plant_abstractions must be a non-empty object")
    return data


def validate_contract(contract: Mapping[str, Any], grbl_root: Path) -> Dict[str, Any]:
    violations: List[Dict[str, Any]] = []
    observed_firmware: Dict[str, Dict[str, Optional[int]]] = {}
    all_constants: Dict[str, int] = {}
    for relative, expected_values in contract["firmware_constants"].items():
        path = grbl_root / relative
        if not path.is_file():
            violations.append({"kind": "missing_source", "path": relative})
            continue
        actual_values = parse_numeric_defines(path.read_text(encoding="utf-8", errors="replace"))
        observed_firmware[relative] = {}
        for name, expected in expected_values.items():
            actual = actual_values.get(name)
            observed_firmware[relative][name] = actual
            if actual is not None:
                if name in all_constants and all_constants[name] != actual:
                    violations.append({"kind": "duplicate_constant", "name": name, "values": [all_constants[name], actual]})
                all_constants[name] = actual
            if actual != expected:
                violations.append(
                    {"kind": "firmware_drift", "path": relative, "name": name, "expected": expected, "actual": actual}
                )

    plant = PaperPlantConfig()
    observed_plant: Dict[str, Any] = {}
    for name, rule in contract["plant_abstractions"].items():
        actual = getattr(plant, name, None)
        observed_plant[name] = actual
        expected = rule.get("expected")
        if actual != expected:
            violations.append({"kind": "plant_drift", "name": name, "expected": expected, "actual": actual})
            continue
        if rule.get("kind") == "scaled_from_firmware":
            firmware_value = all_constants.get(str(rule.get("firmware_constant")))
            numerator = rule.get("scale_numerator")
            denominator = rule.get("scale_denominator")
            if not isinstance(firmware_value, int) or not isinstance(numerator, int) or not isinstance(denominator, int) or denominator <= 0:
                violations.append({"kind": "invalid_scale_rule", "name": name})
            elif firmware_value * numerator != actual * denominator:
                violations.append(
                    {
                        "kind": "scale_drift",
                        "name": name,
                        "firmware_value": firmware_value,
                        "plant_value": actual,
                        "numerator": numerator,
                        "denominator": denominator,
                    }
                )
        if rule.get("kind") == "threshold_abstraction":
            samples = all_constants.get(str(rule.get("firmware_samples_constant")))
            threshold = all_constants.get(str(rule.get("firmware_threshold_constant")))
            if not isinstance(samples, int) or not isinstance(threshold, int) or actual != threshold or threshold > samples:
                violations.append(
                    {"kind": "threshold_drift", "name": name, "firmware_samples": samples, "firmware_threshold": threshold, "plant_value": actual}
                )

    return {
        "suite": "paper_firmware_contract",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not violations else "fail",
        "grbl_root": str(grbl_root.resolve()),
        "machine": contract.get("machine"),
        "observed_firmware": observed_firmware,
        "observed_plant": observed_plant,
        "violations": violations,
        "evidence_boundary": contract.get("evidence_boundary"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="paper firmware/Plant contract validator")
    parser.add_argument("--grbl-root", type=Path, default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")))
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        contract = load_contract(args.contract)
        report = validate_contract(contract, args.grbl_root.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "suite": "paper_firmware_contract",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "fail",
            "grbl_root": str(args.grbl_root.resolve()),
            "violations": [{"kind": "invalid_contract", "detail": str(exc)}],
        }
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = args.json_out or RESULTS / "paper_firmware_contract.json"
    if not path.is_absolute():
        path = FZ_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
