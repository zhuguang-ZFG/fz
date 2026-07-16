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


def _percent(summary: Dict[str, Any], key: str) -> Optional[float]:
    section = summary.get(key)
    if not isinstance(section, dict):
        return None
    count = section.get("count")
    covered = section.get("covered")
    if not isinstance(count, int) or count <= 0 or not isinstance(covered, int):
        return None
    return round(covered * 100.0 / count, 2)


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
                    "summary": summary,
                }
    return result


def _write_report(report: Dict[str, Any]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "coverage_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="native product core coverage")
    parser.add_argument(
        "--grbl-root",
        type=Path,
        default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")),
    )
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xC0FFEE)
    parser.add_argument("--iterations", type=int, default=20000)
    args = parser.parse_args(list(argv) if argv is not None else None)

    grbl_root = args.grbl_root.resolve()
    compiler, kind = native_tests.find_compiler()
    profdata_tool = _tool("llvm-profdata.exe" if os.name == "nt" else "llvm-profdata", compiler)
    cov_tool = _tool("llvm-cov.exe" if os.name == "nt" else "llvm-cov", compiler)
    output = RESULTS / ("product_core_coverage.exe" if os.name == "nt" else "product_core_coverage")
    profraw = RESULTS / "product_core_coverage.profraw"
    profdata = RESULTS / "product_core_coverage.profdata"
    wanted = ["PaperSystemCore.h", "WebUI/BTStateCore.h"]
    report: Dict[str, Any] = {
        "suite": "native_product_core_coverage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "grbl_root": str(grbl_root),
        "compiler": str(compiler) if compiler else None,
        "compiler_kind": kind,
        "llvm_profdata": str(profdata_tool) if profdata_tool else None,
        "llvm_cov": str(cov_tool) if cov_tool else None,
        "seed": args.seed,
        "iterations": args.iterations,
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
        _write_report(report)
        print(report["stderr"], file=sys.stderr, end="")
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
    report["status"] = "pass" if all(name in files for name in wanted) else "fail"
    _write_report(report)
    for name, item in files.items():
        print(
            f"{name}: lines={item.get('lines_percent')}% "
            f"functions={item.get('functions_percent')}% regions={item.get('regions_percent')}%"
        )
    print(f"native_product_core_coverage status={report['status']} report={RESULTS / 'coverage_summary.json'}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
