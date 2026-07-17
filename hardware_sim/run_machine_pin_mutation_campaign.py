#!/usr/bin/env python3
"""Prove the existing firmware pin checker rejects pre-flash defects."""
from __future__ import annotations

import argparse
import copy
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from run_machine_pin_erc import DEFAULT_CONTRACT, RESULTS, load_contract, validate_contract


def _mutated_root(source: Path, old: str, new: str, root: Path) -> Path:
    text = source.read_text(encoding="utf-8", errors="replace")
    if text.count(old) != 1:
        raise ValueError(f"mutation anchor count for {old!r} was {text.count(old)}, expected 1")
    target = root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.replace(old, new), encoding="utf-8")
    return root


def run_campaign(grbl_root: Path, contract_path: Path = DEFAULT_CONTRACT) -> Dict[str, Any]:
    grbl_root = grbl_root.resolve()
    contract = load_contract(contract_path)
    source = grbl_root / str(contract["machine"])
    cases: List[Dict[str, Any]] = []

    def record(name: str, report: Dict[str, Any], expected_kind: Optional[str]) -> None:
        kinds = sorted({str(item.get("kind")) for item in report.get("errors", []) if isinstance(item, dict)})
        passed = report.get("status") == "pass" if expected_kind is None else report.get("status") == "fail" and expected_kind in kinds
        cases.append({"name": name, "expected": expected_kind or "pass", "passed": passed, "observed_error_kinds": kinds, "errors": report.get("errors", [])[:3]})

    record("valid_baseline", validate_contract(copy.deepcopy(contract), grbl_root), None)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        record("output_on_input_only_gpio", validate_contract(copy.deepcopy(contract), _mutated_root(source, "#define X_STEP_PIN              GPIO_NUM_2", "#define X_STEP_PIN              GPIO_NUM_34", root)), "input_only_output")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        record("physical_pin_collision", validate_contract(copy.deepcopy(contract), _mutated_root(source, "#define Y_STEP_PIN              GPIO_NUM_13", "#define Y_STEP_PIN              GPIO_NUM_14", root)), "pin_collision")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        record("uncontracted_safety_pin", validate_contract(copy.deepcopy(contract), _mutated_root(source, "#define X_STEP_PIN              GPIO_NUM_2", "#define X_STEP_PIN              GPIO_NUM_2\n#define NEW_SAFETY_OUTPUT_PIN GPIO_NUM_22", root)), "uncontracted_pin_macro")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        record("invalid_gpio_number", validate_contract(copy.deepcopy(contract), _mutated_root(source, "#define X_STEP_PIN              GPIO_NUM_2", "#define X_STEP_PIN              GPIO_NUM_40", root)), "invalid_gpio")
    narrow = copy.deepcopy(contract)
    narrow["i2so_width"] = 7
    record("i2s_expander_overflow", validate_contract(narrow, grbl_root), "i2so_out_of_range")
    unwaived = copy.deepcopy(contract)
    del unwaived["strapping_output_waivers"]["X_STEP_PIN"]
    record("unreviewed_boot_strapping_output", validate_contract(unwaived, grbl_root), "strapping_output")

    failures = [case for case in cases if not case["passed"]]
    mutants = [case for case in cases if case["expected"] != "pass"]
    return {
        "suite": "machine_pin_checker_mutation_campaign",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not failures else "fail",
        "baseline_passed": cases[0]["passed"],
        "mutation_score": {"killed": sum(1 for case in mutants if case["passed"]), "total": len(mutants)},
        "cases": cases,
        "failures": failures,
        "evidence_boundary": "Temporary firmware-header mutations prove checker sensitivity; they do not modify product files or prove physical hardware/HIL.",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Firmware pin checker defect-injection campaign")
    parser.add_argument("--grbl-root", type=Path, default=Path("D:/Users/Grbl_Esp32"))
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json-out", type=Path, default=RESULTS / "machine_pin_mutations.json")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = run_campaign(args.grbl_root, args.contract)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"suite": "machine_pin_checker_mutation_campaign", "timestamp": datetime.now(timezone.utc).isoformat(), "status": "fail", "mutation_score": {"killed": 0, "total": 6}, "failures": [{"name": "campaign_setup", "detail": str(exc)}]}
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "mutation_score": report["mutation_score"], "report": str(args.json_out)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
