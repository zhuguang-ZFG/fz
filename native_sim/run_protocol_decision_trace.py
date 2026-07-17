#!/usr/bin/env python3
"""Compile and run the product-owned protocol decision core on the host."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import run_product_core_tests as native_tests


FZ_ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
SOURCE = HERE / "protocol_decision_trace.cpp"


def build_command(compiler: Path, grbl_root: Path, output: Path) -> List[str]:
    return [
        str(compiler),
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-iquote",
        str(grbl_root / "Grbl_Esp32" / "src"),
        str(SOURCE),
        "-o",
        str(output),
    ]


def run_trace(
    lines: Sequence[str],
    grbl_root: Path,
    paper_running: bool = False,
    modal_motion_active: bool = False,
    stateful_modal: bool = False,
    now_ms: int = 0,
    last_notice_ms: int = 0,
) -> Dict[str, Any]:
    compiler, _ = native_tests.find_compiler()
    if compiler is None:
        raise RuntimeError("no C++ compiler found")
    header = grbl_root / "Grbl_Esp32" / "src" / "ProtocolDecisionCore.h"
    if not header.is_file():
        raise RuntimeError(f"missing product header: {header}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    output = RESULTS / ("protocol_decision_trace.exe" if os.name == "nt" else "protocol_decision_trace")
    build = subprocess.run(
        build_command(compiler, grbl_root, output),
        cwd=str(FZ_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if build.returncode != 0:
        raise RuntimeError(build.stderr or build.stdout or "protocol decision build failed")
    command = [str(output), "--now-ms", str(now_ms), "--last-notice-ms", str(last_notice_ms)]
    if paper_running:
        command.append("--paper-running")
    if modal_motion_active:
        command.append("--modal-motion-active")
    if stateful_modal:
        command.append("--stateful-modal")
    run = subprocess.run(
        command,
        cwd=str(FZ_ROOT),
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    if run.returncode != 0:
        raise RuntimeError(run.stderr or run.stdout or "protocol decision trace failed")
    trace_text, notice_text = run.stdout.strip().split("\n", 1)
    return {
        "lines": json.loads(trace_text),
        "notice": json.loads(notice_text),
        "compiler": str(compiler),
        "header": str(header),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="product protocol decision native trace")
    parser.add_argument("--grbl-root", type=Path, default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")))
    parser.add_argument("--paper-running", action="store_true")
    parser.add_argument("--modal-motion-active", action="store_true")
    parser.add_argument("--stateful-modal", action="store_true")
    parser.add_argument("--now-ms", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--last-notice-ms", type=lambda value: int(value, 0), default=0)
    parser.add_argument("lines", nargs="*")
    args = parser.parse_args(list(argv) if argv is not None else None)
    lines = args.lines or ["G0 X1", "G1 X1 F100", "G2 X1 Y1 I0 J1", "G3 X0 Y0 I-1 J0", "G10 L2 P1 X0", "G20", "G38.2 Z-1 F10", "G92 X0"]
    report: Dict[str, Any] = {
        "suite": "product_protocol_decision_trace",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "fail",
        "grbl_root": str(args.grbl_root.resolve()),
    }
    try:
        report.update(
            run_trace(
                lines,
                args.grbl_root.resolve(),
                paper_running=args.paper_running,
                modal_motion_active=args.modal_motion_active,
                stateful_modal=args.stateful_modal,
                now_ms=args.now_ms,
                last_notice_ms=args.last_notice_ms,
            )
        )
        report["status"] = "pass"
    except RuntimeError as exc:
        report["error"] = str(exc)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "protocol_decision_trace.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
