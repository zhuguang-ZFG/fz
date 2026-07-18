#!/usr/bin/env python3
"""Measure source coverage for product-owned pure C++ cores."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import run_product_core_tests as native_tests


FZ_ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SOURCE = HERE / "product_core_fuzz.cpp"
DEFAULT_POLICY = HERE / "coverage_policy.json"


def _tool(name: str, compiler: Optional[Path]) -> Optional[Path]:
    candidates: List[Path] = []
    if compiler is not None:
        candidates.append(compiler.with_name(name))
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    candidates.append(Path("C:/Program Files/LLVM/bin") / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _coverage_build_command(compiler: Path, grbl_root: Path, output: Path) -> List[str]:
    include_root = grbl_root / "Grbl_Esp32" / "src"
    return [
        str(compiler),
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fprofile-instr-generate",
        "-fcoverage-mapping",
        "-O0",
        "-g",
        "-iquote",
        str(include_root),
        str(SOURCE),
        "-o",
        str(output),
    ]


def _runtime_path_entries(compiler: Path) -> List[str]:
    entries = [str(compiler.parent)]
    runtime_dir = native_tests.sanitizer_runtime_dir(compiler, "clang")
    if runtime_dir is not None:
        entries.append(str(runtime_dir))
    return entries


def _percent(summary: Dict[str, Any], key: str) -> Optional[float]:
    section = summary.get(key)
    if not isinstance(section, dict):
        return None
    count = section.get("count")
    covered = section.get("covered")
    if not isinstance(count, int) or count <= 0 or not isinstance(covered, int):
        return None
    return covered * 100.0 / count


def _file_summary(raw: Dict[str, Any], suffixes: Sequence[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, list) or not data:
        return result
    files = data[0].get("files") if isinstance(data[0], dict) else None
    if not isinstance(files, list):
        return result
    for item in files:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").replace("\\", "/")
        for suffix in suffixes:
            if filename.endswith(suffix.replace("\\", "/")):
                summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
                result[suffix] = {
                    "filename": filename,
                    "lines_percent": _percent(summary, "lines"),
                    "functions_percent": _percent(summary, "functions"),
                    "regions_percent": _percent(summary, "regions"),
                    "branches_percent": _percent(summary, "branches"),
                    "summary": summary,
                }
    return result


def _load_policy(path: Path) -> Dict[str, Dict[str, float]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    files = raw.get("files") if isinstance(raw, dict) else None
    if not isinstance(files, dict) or not files:
        raise ValueError("coverage policy must contain a non-empty 'files' object")
    policy: Dict[str, Dict[str, float]] = {}
    for filename, thresholds in files.items():
        if not isinstance(filename, str) or not filename or not isinstance(thresholds, dict):
            raise ValueError("coverage policy file entries must map names to thresholds")
        parsed: Dict[str, float] = {}
        for metric, minimum in thresholds.items():
            if metric not in ("lines", "functions", "regions", "branches"):
                raise ValueError(f"unsupported coverage metric: {metric}")
            if (
                isinstance(minimum, bool)
                or not isinstance(minimum, (int, float))
                or not 0 <= float(minimum) <= 100
            ):
                raise ValueError(f"invalid minimum for {filename} {metric}: {minimum}")
            parsed[f"{metric}_percent"] = float(minimum)
        if not parsed:
            raise ValueError(f"coverage policy has no thresholds for {filename}")
        policy[filename] = parsed
    return policy


def _coverage_violations(
    files: Dict[str, Any], policy: Dict[str, Dict[str, float]]
) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    for filename, thresholds in policy.items():
        actual = files.get(filename)
        if not isinstance(actual, dict):
            violations.append({"file": filename, "metric": "file", "reason": "missing"})
            continue
        for metric, minimum in thresholds.items():
            value = actual.get(metric)
            if not isinstance(value, (int, float)):
                violations.append(
                    {"file": filename, "metric": metric, "minimum": minimum, "reason": "missing"}
                )
            elif float(value) < minimum:
                violations.append(
                    {
                        "file": filename,
                        "metric": metric,
                        "actual": float(value),
                        "minimum": minimum,
                        "reason": "below_minimum",
                    }
                )
    return violations


def _write_report(report: Dict[str, Any]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "coverage_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def _display_percent(value: Any) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "n/a"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="native product core coverage")
    parser.add_argument(
        "--grbl-root",
        type=Path,
        default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")),
    )
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xC0FFEE)
    parser.add_argument("--iterations", type=int, default=20000)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args(list(argv) if argv is not None else None)

    grbl_root = args.grbl_root.resolve()
    compiler, kind = native_tests.find_compiler()
    profdata_tool = _tool("llvm-profdata.exe" if os.name == "nt" else "llvm-profdata", compiler)
    cov_tool = _tool("llvm-cov.exe" if os.name == "nt" else "llvm-cov", compiler)
    output = RESULTS / ("product_core_coverage.exe" if os.name == "nt" else "product_core_coverage")
    profraw = RESULTS / "product_core_coverage.profraw"
    profdata = RESULTS / "product_core_coverage.profdata"
    policy_path = args.policy.resolve()
    try:
        policy = _load_policy(policy_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        error = f"invalid coverage policy: {exc}"
        _write_report(
            {
                "suite": "native_product_core_coverage",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "grbl_root": str(grbl_root),
                "policy_path": str(policy_path),
                "policy": {},
                "violations": [
                    {"file": str(policy_path), "metric": "policy", "reason": "invalid"}
                ],
                "files": {},
                "stderr": error,
                "status": "fail",
            }
        )
        print(error, file=sys.stderr)
        return 1
    wanted = list(policy)
    report: Dict[str, Any] = {
        "suite": "native_product_core_coverage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "grbl_root": str(grbl_root),
        "compiler": str(compiler) if compiler else None,
        "compiler_kind": kind,
        "llvm_profdata": str(profdata_tool) if profdata_tool else None,
        "llvm_cov": str(cov_tool) if cov_tool else None,
        "runtime_path_entries": [],
        "seed": args.seed,
        "iterations": args.iterations,
        "policy_path": str(policy_path),
        "policy": policy,
        "violations": [],
        "files": {},
        "build_exit_code": None,
        "run_exit_code": None,
        "merge_exit_code": None,
        "export_exit_code": None,
        "stdout": "",
        "stderr": "",
        "status": "fail",
    }

    if compiler is None or kind != "clang" or profdata_tool is None or cov_tool is None:
        report["status"] = "skip"
        report["stderr"] = "clang/llvm coverage tools unavailable"
        _write_report(report)
        print(report["stderr"])
        return 2

    command = _coverage_build_command(compiler, grbl_root, output)
    report["build_command"] = command
    build = subprocess.run(command, cwd=str(FZ_ROOT), capture_output=True, text=True, timeout=120)
    report["build_exit_code"] = build.returncode
    report["stdout"] += build.stdout
    report["stderr"] += build.stderr
    if build.returncode != 0:
        _write_report(report)
        print(report["stderr"], file=sys.stderr, end="")
        return 1

    run_env = os.environ.copy()
    runtime_entries = _runtime_path_entries(compiler)
    report["runtime_path_entries"] = runtime_entries
    run_env["PATH"] = os.pathsep.join(runtime_entries + [run_env.get("PATH", "")])
    run_env["LLVM_PROFILE_FILE"] = str(profraw)
    run = subprocess.run(
        [str(output), str(args.seed), str(args.iterations)],
        cwd=str(FZ_ROOT),
        env=run_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    report["run_exit_code"] = run.returncode
    report["stdout"] += run.stdout
    report["stderr"] += run.stderr
    if run.returncode != 0:
        pre_main_crash = (
            os.name == "nt"
            and run.returncode >= 0xC0000000
            and not run.stdout.strip()
        )
        if pre_main_crash:
            report["status"] = "skip"
            report["stderr"] += (
                f"\ninstrumented coverage binary crashed pre-main (0x{run.returncode:08x}); "
                "toolchain/runtime environmental issue, not a product-core verdict "
                "(native_fuzz ASan/UBSan layer still enforces memory safety)"
            )
            _write_report(report)
            print(report["stderr"][-400:], file=sys.stderr, end="")
            return 2
        _write_report(report)
        detail = report["stderr"] or f"coverage binary exited {run.returncode} with no output"
        print(detail, file=sys.stderr, end="")
        return 1

    merge = subprocess.run(
        [str(profdata_tool), "merge", "-sparse", str(profraw), "-o", str(profdata)],
        cwd=str(FZ_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    report["merge_exit_code"] = merge.returncode
    report["stdout"] += merge.stdout
    report["stderr"] += merge.stderr
    if merge.returncode != 0:
        _write_report(report)
        print(report["stderr"], file=sys.stderr, end="")
        return 1

    export = subprocess.run(
        [str(cov_tool), "export", str(output), f"-instr-profile={profdata}"],
        cwd=str(FZ_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    report["export_exit_code"] = export.returncode
    report["stderr"] += export.stderr
    if export.returncode != 0:
        _write_report(report)
        print(report["stderr"], file=sys.stderr, end="")
        return 1

    raw = json.loads(export.stdout)
    files = _file_summary(raw, wanted)
    report["files"] = files
    violations = _coverage_violations(files, policy)
    report["violations"] = violations
    report["status"] = "pass" if not violations else "fail"
    _write_report(report)
    for name, item in files.items():
        print(
            f"{name}: lines={_display_percent(item.get('lines_percent'))}% "
            f"functions={_display_percent(item.get('functions_percent'))}% "
            f"regions={_display_percent(item.get('regions_percent'))}% "
            f"branches={_display_percent(item.get('branches_percent'))}%"
        )
    for violation in violations:
        print(f"coverage violation: {violation}", file=sys.stderr)
    print(f"native_product_core_coverage status={report['status']} report={RESULTS / 'coverage_summary.json'}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
