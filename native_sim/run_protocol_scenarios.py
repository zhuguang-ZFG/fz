#!/usr/bin/env python3
"""Run validated product protocol scenarios and minimize failing sequences."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from run_protocol_decision_trace import run_trace
from scenario_contract import SCENARIO_DIR, load_scenario, minimize_lines, write_json

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
POLICY_SOURCE = HERE / "product_policy_trace.cpp"




def scenario_sequence(data: Dict[str, Any]) -> List[str]:
    return list(data.get("events", data.get("lines", [])))


def trace_items(trace: Any) -> List[Dict[str, Any]]:
    return trace if isinstance(trace, list) else trace["lines"]
def run_policy_trace(data: Dict[str, Any], grbl_root: Path) -> List[Dict[str, Any]]:
    import run_product_core_tests as native_tests
    compiler, _ = native_tests.find_compiler()
    if compiler is None:
        raise RuntimeError("no C++ compiler found")
    output = RESULTS / ("product_policy_trace.exe" if os.name == "nt" else "product_policy_trace")
    command = [str(compiler), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-iquote", str(grbl_root / "Grbl_Esp32" / "src"), str(POLICY_SOURCE), "-o", str(output)]
    build = subprocess.run(command, cwd=str(HERE.parent), capture_output=True, text=True, timeout=120)
    if build.returncode != 0:
        raise RuntimeError(build.stderr or build.stdout or "policy trace build failed")
    domain = data["domain"]
    if domain == "license":
        config = data["license"]
        values = []
        licensed = False
        for supplied in data["lines"]:
            values.append(["license", config["chip_high"], config["chip_low"], config["key_high"], config["key_low"], supplied, "licensed" if licensed else "blocked"])
            if supplied == "expected":
                licensed = True
        results = []
        for args in values:
            run = subprocess.run([str(output), *args], cwd=str(HERE.parent), capture_output=True, text=True, timeout=30)
            if run.returncode != 0:
                raise RuntimeError(run.stderr or run.stdout or "license policy trace failed")
            results.append(json.loads(run.stdout))
        return results
    run = subprocess.run([str(output), domain], cwd=str(HERE.parent), input="\n".join(data["events"]) + "\n", capture_output=True, text=True, timeout=30)
    if run.returncode != 0:
        raise RuntimeError(run.stderr or run.stdout or "policy trace failed")
    return json.loads(run.stdout)
def evaluate(data: Dict[str, Any], trace: Any) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    sequence = scenario_sequence(data)
    for index, (expected, actual) in enumerate(zip(data["expect"], trace_items(trace))):
        mismatches = {
            key: {"expected": value, "actual": actual.get(key)}
            for key, value in expected.items()
            if actual.get(key) != value
        }
        if mismatches:
            failures.append({"index": index, "line": sequence[index], "mismatches": mismatches})
    return failures


def trace_for(data: Dict[str, Any], lines: Sequence[str], grbl_root: Path) -> Dict[str, Any]:
    return run_trace(
        lines,
        grbl_root,
        paper_running=data.get("paper_running", False),
        modal_motion_active=data.get("modal_motion_active", False),
        stateful_modal=data.get("stateful_modal", False),
    )


def minimize_failure(data: Dict[str, Any], grbl_root: Path, failure: Dict[str, Any]) -> List[str]:
    target_line = failure["line"]
    target_mismatches = failure["mismatches"]

    def still_fails(lines: Sequence[str]) -> bool:
        if target_line not in lines:
            return False
        trial_data = dict(data)
        trial_data["lines"] = list(lines)
        trial_data["events"] = list(lines)
        trace = run_policy_trace(trial_data, grbl_root) if data.get("domain") in {"license", "paper_bt_ack"} else trace_for(trial_data, lines, grbl_root)
        actual = trace_items(trace)[list(lines).index(target_line)]
        return any(actual.get(key) != detail["expected"] for key, detail in target_mismatches.items())

    return minimize_lines(scenario_sequence(data), still_fails)


def run_scenario(path: Path, grbl_root: Path, shrink: bool = True) -> Dict[str, Any]:
    data = load_scenario(path)
    trace = run_policy_trace(data, grbl_root) if data.get("domain") in {"license", "paper_bt_ack"} else trace_for(data, data["lines"], grbl_root)
    failures = evaluate(data, trace)
    report: Dict[str, Any] = {
        "name": data["name"],
        "path": path.relative_to(HERE.parent).as_posix(),
        "status": "pass" if not failures else "fail",
        "lines": scenario_sequence(data),
        "trace": trace_items(trace),
        "failures": failures,
    }
    if failures and shrink:
        minimal = minimize_failure(data, grbl_root, failures[0])
        report["minimal_failure"] = {"target": failures[0], "lines": minimal}
        report["minimal_regression_case"] = {
            "name": data["name"] + "_minimal_regression",
            "domain": data.get("domain", "protocol"),
            "lines": minimal,
            "source_failure": failures[0],
        }
    return report


def collect(names: Sequence[str]) -> List[Path]:
    available = {path.stem: path for path in sorted(SCENARIO_DIR.glob("*.json"))}
    if not names:
        return list(available.values())
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ValueError(f"unknown scenarios: {unknown}; allowed: {sorted(available)}")
    return [available[name] for name in names]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="run product protocol policy scenarios")
    parser.add_argument("--grbl-root", type=Path, default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")))
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--no-shrink", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report: Dict[str, Any] = {
        "suite": "product_protocol_scenarios",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "fail",
        "grbl_root": str(args.grbl_root.resolve()),
        "scenarios": [],
    }
    try:
        paths = collect(args.only)
        report["scenarios"] = [
            run_scenario(path, args.grbl_root.resolve(), shrink=not args.no_shrink)
            for path in paths
        ]
        report["status"] = "pass" if paths and all(item["status"] == "pass" for item in report["scenarios"]) else "fail"
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        report["error"] = str(exc)
    write_json(RESULTS / "protocol_scenarios.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
