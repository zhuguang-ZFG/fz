#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent closed loop (R38/R39): gate → observe → on hard fail sim_rerun → re-gate.

EDA analogy: run ERC, fix nets, re-ERC — not "open fab website yet".
Always leaves results/agent_observe_last.md for the next agent turn.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


FZ_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> int:
    print("LOOP:", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(FZ_ROOT), env=os.environ.copy()).returncode


def _print_observe_pointer() -> None:
    obs = FZ_ROOT / "results" / "agent_observe_last.json"
    md = FZ_ROOT / "results" / "agent_observe_last.md"
    print(f"LOOP: observe md={md}", flush=True)
    if not obs.is_file():
        _run([sys.executable, str(FZ_ROOT / "scripts" / "agent_observe.py"), "--quiet"])
    try:
        data = json.loads(obs.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    s = data.get("summary") or {}
    print(
        f"LOOP: observe hard={s.get('hard_findings')} soft={s.get('soft_findings')} "
        f"block_done={s.get('agent_should_block_done_claim')} "
        f"prefer_standard={s.get('agent_should_prefer_standard')}",
        flush=True,
    )
    for a in (data.get("next_actions") or [])[:5]:
        print(f"LOOP: next → {a}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="agent_gate + observe + one sim_rerun cycle")
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
    _print_observe_pointer()
    if rc == 0:
        print("LOOP: gate green on first try")
        if args.honesty:
            return _run(
                [
                    sys.executable,
                    str(FZ_ROOT / "scripts" / "release_honesty.py"),
                    "--require-agent-gate",
                    "--allow-pending-hil",
                    "--max-age-hours",
                    "24",
                ]
            )
        return 0

    print("LOOP: gate failed — sim_rerun --from-last")
    rr = _run([sys.executable, str(FZ_ROOT / "scripts" / "sim_rerun.py"), "--from-last"])
    _run([sys.executable, str(FZ_ROOT / "scripts" / "agent_observe.py"), "--quiet"])
    _print_observe_pointer()
    if args.no_reregate:
        return rr or rc

    print("LOOP: re-run agent_gate")
    rc2 = _run(gate)
    _print_observe_pointer()
    if rc2 == 0 and args.honesty:
        return _run(
            [
                sys.executable,
                str(FZ_ROOT / "scripts" / "release_honesty.py"),
                "--require-agent-gate",
                "--allow-pending-hil",
                "--max-age-hours",
                "24",
            ]
        )
    return rc2


if __name__ == "__main__":
    raise SystemExit(main())
