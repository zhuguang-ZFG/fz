#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Release honesty check — EDA-inspired (KiCad ERC/DRC before fab).

Does NOT flash boards. Combines:
  - last agent_gate / SIL artifacts
  - soft_divergence warnings
  - optional G3/G4 evidence presence vs scope flags
  - forbidden marketing claims in free text

Exit:
  0  verdict ready_for_dev OR ready_to_sign_pending_hil (with --allow-pending-hil)
  1  blocked (hard honesty failure)
  2  missing required inputs when --strict
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
OUT_PATH = RESULTS / "release_honesty_last.json"

FORBIDDEN = [
    (re.compile(r"纸路.*已验证|paper.*verified", re.I), "paper_path_verified"),
    (re.compile(r"BT.*已验证|bluetooth.*verified", re.I), "bt_verified"),
    (re.compile(r"OTA.*已验证|ota.*verified", re.I), "wifi_ota_verified"),
    (re.compile(r"全真仿真|chip.?qemu.*product|仿真即发版", re.I), "sim_equals_ship"),
    (re.compile(r"与\s*grblHAL\s*完全一致|identical to grblhal", re.I), "fork_equals_sim"),
]


def _read_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _file_age_hours(path: Path) -> Optional[float]:
    if not path.is_file():
        return None
    return (time.time() - path.stat().st_mtime) / 3600.0


def _scan_claims(text: str) -> List[str]:
    hits: List[str] = []
    for rx, label in FORBIDDEN:
        if rx.search(text or ""):
            hits.append(label)
    return hits


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="EDA-style release honesty (no hardware)")
    ap.add_argument(
        "--require-agent-gate",
        action="store_true",
        help="require results/agent_gate_last.json overall_status=pass",
    )
    ap.add_argument(
        "--max-age-hours",
        type=float,
        default=24.0,
        help="max age of agent_gate report in hours (default 24h; release --max-age-hours 168)",
    )
    ap.add_argument(
        "--scope",
        type=Path,
        default=None,
        help="release scope yaml (features.paper_path / ota / bluetooth)",
    )
    ap.add_argument(
        "--g3-evidence",
        type=Path,
        default=None,
        help="filled g3 evidence yaml (presence check)",
    )
    ap.add_argument(
        "--g4-evidence",
        type=Path,
        default=None,
        help="filled g4 evidence yaml (presence check)",
    )
    ap.add_argument(
        "--claims-file",
        type=Path,
        action="append",
        default=[],
        help="markdown/text to scan for forbidden ship claims",
    )
    ap.add_argument(
        "--allow-pending-hil",
        action="store_true",
        help="exit 0 even if HIL evidence missing (verdict pending_hil)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="missing agent_gate → exit 2",
    )
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)

    blockers: List[str] = []
    warnings: List[str] = []
    notes: List[str] = []

    gate_path = RESULTS / "agent_gate_last.json"
    gate = _read_json(gate_path)
    age_h = _file_age_hours(gate_path)
    sil_ok = False
    if gate is None:
        msg = "missing results/agent_gate_last.json — run: python scripts/agent_gate.py"
        if args.require_agent_gate or args.strict:
            blockers.append(msg)
        else:
            warnings.append(msg)
    else:
        st = gate.get("overall_status")
        sil_ok = st == "pass"
        if not sil_ok:
            blockers.append(f"agent_gate overall_status={st!r} (need pass)")
        if age_h is not None and age_h > args.max_age_hours:
            blockers.append(
                f"agent_gate report too old: {age_h:.1f}h > {args.max_age_hours}h — re-run gate"
            )
        notes.append(f"agent_gate profile={gate.get('profile')} age_h={age_h}")

    soft = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json") or {}
    high = list(soft.get("high_divergence") or [])
    if high:
        warnings.append(
            "soft high divergence (not auto-block): " + ", ".join(high)
        )
    total_err = int(soft.get("total_err_lines") or 0)
    if total_err:
        notes.append(f"soft total_err_lines={total_err}")

    # scope features
    paper = bt = ota = False
    scope_path = args.scope
    if scope_path is None:
        # default pre-release-min style: no paper/ota
        cand = FZ_ROOT / "release" / "scopes" / "pre-release-min.yaml"
        if cand.is_file():
            scope_path = cand
    if scope_path and scope_path.is_file():
        raw = scope_path.read_text(encoding="utf-8", errors="replace")
        paper = bool(re.search(r"paper_path\s*:\s*true", raw, re.I))
        bt = bool(re.search(r"bluetooth\s*:\s*true", raw, re.I))
        ota = bool(re.search(r"^\s*ota\s*:\s*true", raw, re.I | re.M))
        notes.append(f"scope={scope_path.name} paper={paper} bt={bt} ota={ota}")

    def _evidence_ok(path: Optional[Path]) -> bool:
        if path is None:
            return False
        p = path if path.is_absolute() else FZ_ROOT / path
        if not p.is_file():
            return False
        # reject pure templates left unfilled (heuristic)
        t = p.read_text(encoding="utf-8", errors="replace")
        if "TODO" in t or "template" in p.name.lower() and "pass" not in t.lower():
            # sample-pass files are ok
            if "sample-pass" in p.name or re.search(r"result:\s*[\"']?pass", t, re.I):
                return True
            if "template" in p.name.lower():
                return False
        return True

    def _as_opt_path(p: Optional[Path]) -> Optional[Path]:
        if p is None or not str(p).strip():
            return None
        return p if p.is_absolute() else FZ_ROOT / p

    g3 = _as_opt_path(args.g3_evidence) or _as_opt_path(
        Path(os.environ["G3_EVIDENCE"]) if os.environ.get("G3_EVIDENCE") else None
    )
    g4 = _as_opt_path(args.g4_evidence) or _as_opt_path(
        Path(os.environ["G4_EVIDENCE"]) if os.environ.get("G4_EVIDENCE") else None
    )

    hil_required = bool(paper or bt or ota)
    hil_ok = True
    if paper or bt:
        if not _evidence_ok(g3):
            hil_ok = False
            msg = (
                "scope needs paper/bt HIL evidence — provide --g3-evidence filled YAML "
                "(not unfilled template)"
            )
            if args.allow_pending_hil:
                warnings.append(msg + " [pending allowed]")
            else:
                blockers.append(msg)
    if ota:
        if not _evidence_ok(g4):
            hil_ok = False
            msg = (
                "scope needs OTA evidence — provide --g4-evidence filled YAML "
                "or USB dual-flash merge"
            )
            if args.allow_pending_hil:
                warnings.append(msg + " [pending allowed]")
            else:
                blockers.append(msg)

    if not hil_required:
        hil_ok = True
        notes.append("HIL not required by scope (paper/bt/ota all false)")

    claim_hits: List[str] = []
    for cf in args.claims_file or []:
        cp = cf if Path(cf).is_absolute() else FZ_ROOT / cf
        if cp.is_file():
            claim_hits.extend(_scan_claims(cp.read_text(encoding="utf-8", errors="replace")))
    claim_hits = list(dict.fromkeys(claim_hits))
    if claim_hits:
        blockers.append("forbidden claims in --claims-file: " + ", ".join(claim_hits))

    # verdict
    if not sil_ok or any("agent_gate" in b or "too old" in b for b in blockers):
        verdict = "blocked"
    elif claim_hits:
        verdict = "blocked"
    elif sil_ok and hil_required and not hil_ok:
        verdict = "ready_to_sign_pending_hil" if args.allow_pending_hil else "blocked"
    elif sil_ok and hil_ok and hil_required:
        verdict = "ready_to_sign"
    elif sil_ok:
        verdict = "ready_for_dev"
    else:
        verdict = "blocked"

    report: Dict[str, Any] = {
        "suite": "release_honesty",
        "version": 1,
        "inspired_by": [
            "KiCad ERC/DRC before manufacturing outputs",
            "EasyEDA simulation vs order flow separation",
            "industry SIL vs HIL honesty",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "sil_ok": sil_ok,
        "agent_gate_age_hours": age_h,
        "hil_required": hil_required,
        "hil_ok": hil_ok,
        "soft_high_divergence": high,
        "soft_total_err_lines": total_err,
        "forbidden_claims_hit": claim_hits,
        "blockers": blockers,
        "warnings": warnings,
        "notes": notes,
        "next_commands": {
            "dev_sil": "python scripts/agent_gate.py --profile standard",
            "rerun_fail": "python scripts/sim_rerun.py --from-last",
            "hil": "python scripts/hil_to_gate.py --port COMx",
            "sign_off": "release/SIGN_OFF.template.md",
        },
    }

    out = args.out if args.out.is_absolute() else FZ_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== release_honesty (EDA-style) ===")
    print(f"verdict: {verdict}")
    print(f"sil_ok={sil_ok} hil_required={hil_required} hil_ok={hil_ok}")
    for b in blockers:
        print(f"  BLOCK: {b}")
    for w in warnings:
        print(f"  WARN:  {w}")
    for n in notes:
        print(f"  note:  {n}")
    print(f"report: {out}")

    if verdict == "blocked":
        return 1
    if args.strict and gate is None:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
