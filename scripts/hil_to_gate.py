#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-click HIL evidence → merge YAML → release_gate (community HIL CI pattern).

Without --port (default / offline):
  - runs hil unit tests
  - optionally full_release_smoke (no silicon)
  - prints how to attach a board for G3b/G4

With --port:
  - paper_m30_serial → merge g3 evidence
  - optional dual_flash_usb → merge g4 evidence
  - release_gate with --g3-evidence / --g4-evidence

Does not claim product paper/BT without operator YAML fill for remaining items.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


FZ_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: List[str], cwd: Optional[Path] = None) -> int:
    print("RUN:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd or FZ_ROOT), env=os.environ.copy())
    return proc.returncode


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HIL serial/flash → evidence YAML → release_gate"
    )
    ap.add_argument(
        "--port",
        default=None,
        help="serial port (e.g. COM7). Omit for offline dry path.",
    )
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--results-dir",
        type=Path,
        default=FZ_ROOT / "results",
        help="JSON/YAML output directory",
    )
    ap.add_argument(
        "--with-g4",
        action="store_true",
        help="run USB dual_flash_usb and merge G4 evidence",
    )
    ap.add_argument(
        "--g4-mode",
        choices=("once", "twice"),
        default="once",
        help="dual_flash_usb mode",
    )
    ap.add_argument(
        "--no-expect-paper-log",
        action="store_true",
        help="paper_m30: test_drive / no paper custom logs",
    )
    ap.add_argument(
        "--skip-hil-tests",
        action="store_true",
        help="skip offline hil unittest",
    )
    ap.add_argument(
        "--skip-smoke",
        action="store_true",
        help="skip full_release_smoke after offline tests",
    )
    ap.add_argument(
        "--skip-gate",
        action="store_true",
        help="only produce evidence files; do not call release_gate",
    )
    ap.add_argument(
        "--grbl-root",
        type=Path,
        default=None,
        help="override GRBL_ROOT for dual_flash",
    )
    ap.add_argument(
        "--g3-template",
        type=Path,
        default=FZ_ROOT / "release" / "g3_evidence.template.yaml",
    )
    ap.add_argument(
        "--g4-template",
        type=Path,
        default=FZ_ROOT / "release" / "g4_ota.template.yaml",
    )
    ap.add_argument(
        "--scope-g3",
        type=Path,
        default=FZ_ROOT / "release" / "scopes" / "dev-quick.yaml",
        help="scope when only G3 evidence (paper may still fail-closed if required)",
    )
    ap.add_argument(
        "--scope-g4",
        type=Path,
        default=FZ_ROOT / "release" / "scopes" / "dev-ota.yaml",
    )
    args = ap.parse_args(argv)

    results = (
        args.results_dir
        if args.results_dir.is_absolute()
        else FZ_ROOT / args.results_dir
    )
    results.mkdir(parents=True, exist_ok=True)

    # --- always: offline hil logic tests ---
    if not args.skip_hil_tests:
        rc = _run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "hil",
                "-p",
                "test_*.py",
                "-v",
            ]
        )
        if rc != 0:
            return rc

    if not args.port:
        print(
            "OFFLINE: no --port; HIL serial/flash skipped. "
            "Attach board: python scripts/hil_to_gate.py --port COM7 [--with-g4]"
        )
        if not args.skip_smoke:
            rc = _run([sys.executable, str(FZ_ROOT / "scripts" / "full_release_smoke.py")])
            return rc
        return 0

    # --- on-board path ---
    # R36: G3a serial smoke + archived transcript, then G3b paper sequences
    g3a_json = results / "g3a_serial.json"
    g3a_cmd = [
        sys.executable,
        str(FZ_ROOT / "hil" / "serial_smoke.py"),
        "--port",
        args.port,
        "--baud",
        str(args.baud),
        "--out",
        str(g3a_json),
    ]
    rc_a = _run(g3a_cmd)
    if rc_a != 0:
        print("WARN: serial_smoke (G3a) exit", rc_a, file=sys.stderr)

    g3_json = results / "g3b_paper.json"
    g3_yaml = results / "g3_evidence.filled.yaml"
    paper_cmd = [
        sys.executable,
        str(FZ_ROOT / "hil" / "paper_m30_serial.py"),
        "--port",
        args.port,
        "--baud",
        str(args.baud),
        "--out",
        str(g3_json),
    ]
    if args.no_expect_paper_log:
        paper_cmd.append("--no-expect-paper-log")
    rc = _run(paper_cmd)
    if rc != 0:
        print("WARN: paper_m30_serial exit", rc, file=sys.stderr)
        # still merge if JSON written
    if not g3_json.is_file():
        print("ERROR: missing", g3_json, file=sys.stderr)
        return rc or 1

    # R36: index log paths for operators/agents
    try:
        sys.path.insert(0, str(FZ_ROOT / "hil"))
        from archive_serial_log import write_session_index  # type: ignore

        entries = []
        for p in (g3a_json, g3_json):
            if not p.is_file():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            sl = data.get("serial_log") if isinstance(data, dict) else None
            if isinstance(sl, dict) and sl.get("log_path"):
                entries.append(sl)
        write_session_index(entries)
        print("R36 hil log index: results/hil_log_index.md")
    except Exception as exc:  # noqa: BLE001
        print("WARN: hil log index skip", exc, file=sys.stderr)

    rc_m = _run(
        [
            sys.executable,
            str(FZ_ROOT / "hil" / "merge_evidence_patches.py"),
            "--template",
            str(args.g3_template),
            "--patch-json",
            str(g3_json),
            "--out",
            str(g3_yaml),
        ]
    )
    if rc_m != 0:
        return rc_m

    g4_yaml: Optional[Path] = None
    if args.with_g4:
        grbl = args.grbl_root or Path(os.environ.get("GRBL_ROOT", ""))
        if not grbl or not Path(grbl).is_dir():
            print(
                "ERROR: --with-g4 needs --grbl-root or GRBL_ROOT",
                file=sys.stderr,
            )
            return 2
        g4_json = results / "g4_usb.json"
        g4_yaml = results / "g4_ota.filled.yaml"
        flash_cmd = [
            sys.executable,
            str(FZ_ROOT / "hil" / "dual_flash_usb.py"),
            "--port",
            args.port,
            "--mode",
            args.g4_mode,
            "--grbl-root",
            str(grbl),
            "--out",
            str(g4_json),
        ]
        rc_f = _run(flash_cmd)
        if rc_f != 0:
            print("WARN: dual_flash_usb exit", rc_f, file=sys.stderr)
        if not g4_json.is_file():
            return rc_f or 1
        rc_m4 = _run(
            [
                sys.executable,
                str(FZ_ROOT / "hil" / "merge_evidence_patches.py"),
                "--template",
                str(args.g4_template),
                "--patch-json",
                str(g4_json),
                "--out",
                str(g4_yaml),
            ]
        )
        if rc_m4 != 0:
            return rc_m4

    if args.skip_gate:
        print("skip-gate: evidence at", g3_yaml, g4_yaml or "")
        return 0 if rc == 0 else rc

    # release_gate: G1+G5 always; G3; G4 if with-g4
    only = ["G1", "G3", "G5"]
    scope = args.scope_g4 if args.with_g4 else args.scope_g3
    cmd = [
        sys.executable,
        str(FZ_ROOT / "scripts" / "release_gate.py"),
        "--scope",
        str(scope),
        "--skip-g0",
        "--g3-evidence",
        str(g3_yaml),
    ]
    if g4_yaml is not None:
        only = ["G1", "G3", "G4", "G5"]
        cmd.extend(["--g4-evidence", str(g4_yaml)])
    cmd.extend(["--only", ",".join(only)])

    rc_g = _run(cmd)
    print(
        "NOTE: remaining g3/g4 YAML items (keys/BT/true Wi-Fi OTA) still need operator fill; "
        "this pipeline only patches scriptable serial/USB fields."
    )
    return rc_g


if __name__ == "__main__":
    raise SystemExit(main())
