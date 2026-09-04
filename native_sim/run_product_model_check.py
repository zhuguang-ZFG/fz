#!/usr/bin/env python3
"""Exhaustively check small product state spaces and protocol metamorphic invariants."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import run_product_core_tests as native_tests

HERE = Path(__file__).resolve().parent
FZ_ROOT = HERE.parent
RESULTS = HERE / "results"
SOURCE = HERE / "product_model_check.cpp"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="product finite-state and metamorphic checker")
    parser.add_argument("--grbl-root", type=Path, default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")))
    args = parser.parse_args(list(argv) if argv is not None else None)
    compiler, compiler_kind = native_tests.find_compiler()
    report = {
        "suite": "native_product_model_check",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "fail",
        "grbl_root": str(args.grbl_root.resolve()),
    }
    try:
        required = args.grbl_root.resolve() / "Grbl_Esp32" / "src" / "PaperSearchCore.h"
        if not required.is_file():
            raise RuntimeError(f"missing product header: {required}")
        if compiler is None:
            raise RuntimeError("no C++ compiler found")
        output = RESULTS / ("product_model_check.exe" if os.name == "nt" else "product_model_check")
        RESULTS.mkdir(parents=True, exist_ok=True)
        command = [
            str(compiler), "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-iquote", str(args.grbl_root.resolve() / "Grbl_Esp32" / "src"),
            str(SOURCE), "-o", str(output),
        ]
        if os.name == "nt" and compiler_kind == "gnu":
            # Same rationale as run_product_core_tests.build_command.
            command.extend(["-static-libstdc++", "-static-libgcc", "-static"])
        build = subprocess.run(
            command,
            cwd=str(FZ_ROOT), capture_output=True, text=True, timeout=120,
        )
        if build.returncode != 0:
            raise RuntimeError(f"model checker build failed (exit {build.returncode}): "
                               f"{build.stderr or build.stdout or 'no output'}")
        run = subprocess.run([str(output)], cwd=str(FZ_ROOT), capture_output=True, text=True, timeout=30)
        result = json.loads(run.stdout)
        report.update(result)
        report["status"] = "pass" if run.returncode == 0 and result.get("failures") == 0 else "fail"
        report["stderr"] = run.stderr
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        report["error"] = str(exc)
    path = RESULTS / "product_model_check.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
