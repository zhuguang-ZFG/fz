#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent closed loop: gate → on hard fail, sim_rerun once → re-gate optional.

EDA analogy: run ERC, fix nets, re-ERC — not "open fab website yet".
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


FZ_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> int:
    print("LOOP:", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(FZ_ROOT), env=os.environ.copy()).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="agent_gate + one sim_rerun cycle")
    ap.add_argument("--profile", default="standard")
    ap.add_argument("--hw-fast", action="store_true")
    ap.add_argument(
        "--no-reregate",
        action="store_true",
        help="after sim_rerun, do not run agent_gate again",
    )
    ap.add_argument(
        "--honesty",
        action="store_true",
        help="after success, run release_honesty --allow-pending-hil",
    )
    args = ap.parse_args()

    gate = [
        sys.executable,
        str(FZ_ROOT / "scripts" / "agent_gate.py"),
        "--profile",
        args.profile,
    ]
    if args.hw_fast:
        gate.append("--hw-fast")
    rc = _run(gate)
    if rc == 0:
        print("LOOP: gate green on first try")
        if args.honesty:
            return _run(
                [
                    sys.executable,
                    str(FZ_ROOT / "scripts" / "release_honesty.py"),
                    "--require-agent-gate",
                    "--allow-pending-hil",
                ]
            )
        return 0

    print("LOOP: gate failed — sim_rerun --from-last")
    rr = _run([sys.executable, str(FZ_ROOT / "scripts" / "sim_rerun.py"), "--from-last"])
    if args.no_reregate:
        return rr or rc

    print("LOOP: re-run agent_gate")
    rc2 = _run(gate)
    if rc2 == 0 and args.honesty:
        return _run(
            [
                sys.executable,
                str(FZ_ROOT / "scripts" / "release_honesty.py"),
                "--require-agent-gate",
                "--allow-pending-hil",
            ]
        )
    return rc2


if __name__ == "__main__":
    raise SystemExit(main())
