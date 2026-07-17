#!/usr/bin/env python3
"""Compile and run product-owned pure C++ cores on the PC."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


FZ_ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SOURCE = HERE / "product_core_tests.cpp"


def _existing(path: str) -> Optional[Path]:
    candidate = Path(path)
    return candidate if candidate.is_file() else None


def find_compiler() -> Tuple[Optional[Path], str]:
    configured = os.environ.get("CXX", "").strip()
    candidates = [
        (_existing(configured), "gnu") if configured else (None, ""),
        (Path(found), "clang") if (found := shutil.which("clang++")) else (None, ""),
        (_existing("C:/Program Files/LLVM/bin/clang++.exe"), "clang"),
        (Path(found), "gnu") if (found := shutil.which("g++")) else (None, ""),
    ]
    mingw_root = Path.home() / "scoop" / "apps" / "mingw"
    if mingw_root.is_dir():
        for candidate in sorted(mingw_root.glob("*/bin/g++.exe"), reverse=True):
            candidates.append((candidate, "gnu"))
    for path, kind in candidates:
        if path is not None and path.is_file():
            return path.resolve(), kind
    return None, ""


def build_command(compiler: Path, kind: str, grbl_root: Path, output: Path) -> List[str]:
    include_root = grbl_root / "Grbl_Esp32" / "src"
    command = [
        str(compiler),
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fno-omit-frame-pointer",
        "-iquote",
        str(include_root),
        str(SOURCE),
        "-o",
        str(output),
    ]
    if kind in ("clang", "gnu"):
        command[5:5] = ["-fsanitize=address,undefined"]
    return command


def sanitizer_runtime_dir(compiler: Path, kind: str) -> Optional[Path]:
    if kind != "clang" or os.name != "nt":
        return None
    llvm_root = compiler.parent.parent
    matches = sorted(llvm_root.glob("lib/clang/*/lib/windows/clang_rt.asan_dynamic-x86_64.dll"), reverse=True)
    return matches[0].parent if matches else None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="native product core tests")
    parser.add_argument(
        "--grbl-root",
        type=Path,
        default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    grbl_root = args.grbl_root.resolve()
    required = [
        grbl_root / "Grbl_Esp32" / "src" / "PaperSystemCore.h",
        grbl_root / "Grbl_Esp32" / "src" / "PaperSearchCore.h",
        grbl_root / "Grbl_Esp32" / "src" / "WebUI" / "BTStateCore.h",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    compiler, kind = find_compiler()
    RESULTS.mkdir(parents=True, exist_ok=True)
    output = RESULTS / ("product_core_tests.exe" if os.name == "nt" else "product_core_tests")
    report = {
        "suite": "native_product_core",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "grbl_root": str(grbl_root),
        "compiler": str(compiler) if compiler else None,
        "sanitizers": ["address", "undefined"] if compiler else [],
        "sanitizer_runtime_dir": None,
        "required_headers": [str(path) for path in required],
        "missing": missing,
        "build_command": [],
        "build_exit_code": None,
        "run_exit_code": None,
        "stdout": "",
        "stderr": "",
        "status": "fail",
    }
    if missing or compiler is None:
        report["stderr"] = "missing product headers" if missing else "no C++ compiler found"
        (RESULTS / "last_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(report["stderr"], file=sys.stderr)
        return 2

    command = build_command(compiler, kind, grbl_root, output)
    report["build_command"] = command
    build = subprocess.run(command, cwd=str(FZ_ROOT), capture_output=True, text=True, timeout=120)
    report["build_exit_code"] = build.returncode
    report["stdout"] = build.stdout
    report["stderr"] = build.stderr
    if build.returncode == 0:
        run_env = os.environ.copy()
        runtime_dir = sanitizer_runtime_dir(compiler, kind)
        report["sanitizer_runtime_dir"] = str(runtime_dir) if runtime_dir else None
        if runtime_dir is not None:
            run_env["PATH"] = str(runtime_dir) + os.pathsep + run_env.get("PATH", "")
        run = subprocess.run([str(output)], cwd=str(FZ_ROOT), env=run_env, capture_output=True, text=True, timeout=30)
        report["run_exit_code"] = run.returncode
        report["stdout"] += run.stdout
        report["stderr"] += run.stderr
        report["status"] = "pass" if run.returncode == 0 else "fail"

    (RESULTS / "last_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["stdout"]:
        print(report["stdout"], end="")
    if report["stderr"]:
        print(report["stderr"], file=sys.stderr, end="")
    print(f"native_product_core status={report['status']} report={RESULTS / 'last_report.json'}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
