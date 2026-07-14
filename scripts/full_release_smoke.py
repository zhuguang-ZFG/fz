#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-command pre-release smoke for fz gates (no silicon by default).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


FZ_ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Full release smoke (G1+G5, optional G0/G2/G3/G4)")
    ap.add_argument("--with-g0", action="store_true")
    ap.add_argument("--g0-mode", default="test_drive", choices=("default", "machines", "test_drive"))
    ap.add_argument("--with-cloud", action="store_true", help="enable G2 via dev-cloud scope")
    ap.add_argument("--g3-evidence", type=Path, default=None)
    ap.add_argument("--g4-evidence", type=Path, default=None)
    ap.add_argument(
        "--scope",
        type=Path,
        default=None,
        help="override scope yaml (default pre-release-min or dev-cloud)",
    )
    ap.add_argument(
        "--with-win-full-sim",
        action="store_true",
        help="run scripts/win_full_sim.py first (host SIL stack; not silicon)",
    )
    args = ap.parse_args(argv)

    if args.with_win_full_sim:
        print("RUN: win_full_sim pre-stack")
        w = subprocess.run(
            [sys.executable, str(FZ_ROOT / "scripts" / "win_full_sim.py")],
            cwd=str(FZ_ROOT),
            env=os.environ.copy(),
        )
        if w.returncode != 0:
            return w.returncode

    if args.scope:
        scope = args.scope if args.scope.is_absolute() else FZ_ROOT / args.scope
    elif args.with_cloud:
        scope = FZ_ROOT / "release" / "scopes" / "dev-cloud.yaml"
    else:
        scope = FZ_ROOT / "release" / "scopes" / "pre-release-min.yaml"

    only = ["G1", "G5"]
    if args.with_g0:
        only.insert(0, "G0")
    if args.with_cloud or (scope.name == "dev-cloud.yaml"):
        if "G2" not in only:
            only.insert(-1, "G2")
    if args.g3_evidence:
        only.insert(-1, "G3")
    if args.g4_evidence:
        only.insert(-1, "G4")

    cmd = [
        sys.executable,
        str(FZ_ROOT / "scripts" / "release_gate.py"),
        "--scope",
        str(scope),
        "--only",
        ",".join(only),
        "--g0-mode",
        args.g0_mode,
    ]
    if not args.with_g0:
        cmd.append("--skip-g0")
    if args.g3_evidence:
        cmd.extend(["--g3-evidence", str(args.g3_evidence)])
    if args.g4_evidence:
        cmd.extend(["--g4-evidence", str(args.g4_evidence)])

    print("RUN:", " ".join(cmd))
    env = os.environ.copy()
    proc = subprocess.run(cmd, cwd=str(FZ_ROOT), env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
