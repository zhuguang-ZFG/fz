#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rerun only failed (or named) host-SIL cases — fast Agent fix loop.

Examples:
  python scripts/sim_rerun.py --from-last          # protocol+hardware failed names
  python scripts/sim_rerun.py --protocol undefined_feed,arc_radius
  python scripts/sim_rerun.py --hardware json_move_x10_step_window
  python scripts/sim_rerun.py --list
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence


FZ_ROOT = Path(__file__).resolve().parent.parent


def _load_failed_protocol() -> List[str]:
    p = FZ_ROOT / "protocol_sim" / "results" / "last_report.json"
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    out: List[str] = []
    if isinstance(data, list):
        for c in data:
            if isinstance(c, dict) and c.get("passed") is False and c.get("kind") != "soft":
                out.append(str(c.get("name") or ""))
    return [x for x in out if x]


def _load_failed_hardware() -> List[str]:
    p = FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json"
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    out: List[str] = []
    for c in data.get("cases") or []:
        if isinstance(c, dict) and c.get("passed") is False:
            out.append(str(c.get("name") or ""))
    return [x for x in out if x]


def _load_soft_divergence() -> dict:
    p = FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Rerun failed/named PC sim cases")
    ap.add_argument("--from-last", action="store_true", help="use last_report failed names")
    ap.add_argument("--protocol", default="", help="comma names for protocol_sim --only")
    ap.add_argument("--hardware", default="", help="comma names for hardware_sim --only")
    ap.add_argument("--list", action="store_true", help="list last failures + soft divergence")
    ap.add_argument("--hw-fast", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    proto_names: List[str] = []
    hw_names: List[str] = []
    if args.from_last:
        proto_names.extend(_load_failed_protocol())
        hw_names.extend(_load_failed_hardware())
    if args.protocol.strip():
        proto_names.extend([x.strip() for x in args.protocol.split(",") if x.strip()])
    if args.hardware.strip():
        hw_names.extend([x.strip() for x in args.hardware.split(",") if x.strip()])

    # unique
    proto_names = list(dict.fromkeys(proto_names))
    hw_names = list(dict.fromkeys(hw_names))

    if args.list:
        print("protocol_failed:", proto_names or _load_failed_protocol())
        print("hardware_failed:", hw_names or _load_failed_hardware())
        soft = _load_soft_divergence()
        print("soft_divergence:", json.dumps(soft, ensure_ascii=False, indent=2)[:2000])
        return 0

    if not proto_names and not hw_names:
        print(
            "Nothing to rerun. Use --from-last after a failed gate, or --protocol/--hardware names.\n"
            "  python scripts/sim_rerun.py --list",
            file=sys.stderr,
        )
        return 3

    rc = 0
    env = os.environ.copy()
    if proto_names:
        cmd = [
            sys.executable,
            str(FZ_ROOT / "protocol_sim" / "run_regression.py"),
            "--start-sim",
            "--only",
            ",".join(proto_names),
        ]
        if env.get("GRBL_ROOT"):
            cmd.append("--include-repo-tests")
        print("RUN:", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(FZ_ROOT), env=env)
        rc = r.returncode or rc

    if hw_names:
        cmd = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_hw_sim.py"),
            "--start-sim",
            "--only",
            ",".join(hw_names),
        ]
        if args.hw_fast:
            cmd.append("--fast")
        print("RUN:", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(FZ_ROOT), env=env)
        rc = r.returncode or rc

    print(f"sim_rerun exit={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
