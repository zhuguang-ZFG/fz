#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run QWEN3.0 motion contract / FakeDevice tests for release_gate G2.

Uses QWEN_ROOT and prefers .venv310 (project requires Python 3.10).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TESTS = [
    "tests/test_device_gateway_motion_contract.py",
    "tests/test_device_motion.py",
]


def find_python(qwen_root: Path) -> Path:
    candidates = [
        qwen_root / ".venv310" / "Scripts" / "python.exe",
        qwen_root / ".venv310" / "bin" / "python",
        qwen_root / ".venv" / "Scripts" / "python.exe",
        qwen_root / ".venv" / "bin" / "python",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return Path(sys.executable)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="G2 QWEN contract runner")
    ap.add_argument(
        "--qwen-root",
        type=Path,
        default=Path(os.environ.get("QWEN_ROOT", "D:/QWEN3.0")),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional JSON report path",
    )
    args = ap.parse_args(argv)

    root = args.qwen_root
    if not root.is_dir():
        print(f"ERROR: QWEN_ROOT not found: {root}", file=sys.stderr)
        return 2

    py = find_python(root)
    tests = [t for t in DEFAULT_TESTS if (root / t).is_file()]
    if not tests:
        print("ERROR: no contract test files found", file=sys.stderr)
        return 2

    cmd = [str(py), "-m", "pytest", *tests, "-q", "--tb=line"]
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=300,
    )
    report: Dict[str, Any] = {
        "layer": "G2",
        "status": "pass" if proc.returncode == 0 else "fail",
        "exit_code": proc.returncode,
        "duration_s": round(time.time() - t0, 2),
        "python": str(py),
        "qwen_root": str(root),
        "tests": tests,
        "stdout_tail": (proc.stdout or "")[-3000:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
