#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R34: one-page host-SIL triage for agents (community: readable CI failure surface).

Aggregates agent_gate + protocol/hw last reports + soft divergence into:
  results/triage_last.md
  results/triage_last.json

Also used by agent_gate (R35) to print failure slices on red.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
TRIAGE_MD = RESULTS / "triage_last.md"
TRIAGE_JSON = RESULTS / "triage_last.json"


def _read_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _failed_protocol_cases(limit: int = 12) -> List[Dict[str, Any]]:
    data = _read_json(FZ_ROOT / "protocol_sim" / "results" / "last_report.json")
    out: List[Dict[str, Any]] = []
    if not isinstance(data, list):
        return out
    for c in data:
        if not isinstance(c, dict) or c.get("passed") is not False:
            continue
        if c.get("kind") == "soft":
            continue
        lines = c.get("lines") or []
        bad_lines = []
        for lr in lines:
            if isinstance(lr, dict) and lr.get("ok") is False:
                bad_lines.append(
                    {
                        "line": lr.get("line"),
                        "responses": (lr.get("responses") or [])[:8],
                        "detail": lr.get("detail") or "",
                    }
                )
        out.append(
            {
                "name": c.get("name"),
                "kind": c.get("kind"),
                "detail": c.get("detail") or "",
                "bad_lines": bad_lines[:5],
            }
        )
        if len(out) >= limit:
            break
    return out


def _failed_hardware_cases(limit: int = 8) -> List[Dict[str, Any]]:
    data = _read_json(FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json")
    out: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        return out
    for c in data.get("cases") or []:
        if not isinstance(c, dict) or c.get("passed") is not False:
            continue
        out.append(
            {
                "name": c.get("name"),
                "detail": c.get("detail") or c.get("message") or "",
            }
        )
        if len(out) >= limit:
            break
    return out


def build_triage() -> Dict[str, Any]:
    gate = _read_json(RESULTS / "agent_gate_last.json") or {}
    soft = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json") or {}
    soft_al = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_allowlist_last.json") or {}
    proto_fail = _failed_protocol_cases()
    hw_fail = _failed_hardware_cases()
    layer_fails = []
    if isinstance(gate, dict):
        for L in gate.get("failures") or gate.get("layers") or []:
            if isinstance(L, dict) and L.get("status") == "fail":
                layer_fails.append(
                    {
                        "id": L.get("id"),
                        "name": L.get("name"),
                        "detail": L.get("detail") or "",
                        "log_hint": L.get("log_hint") or "",
                        "exit_code": L.get("exit_code"),
                    }
                )
    log_paths = [
        str(RESULTS / "agent_gate_last.json"),
        str(FZ_ROOT / "protocol_sim" / "results" / "last_report.json"),
        str(FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json"),
        str(FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json"),
        str(FZ_ROOT / "hardware_sim" / "results" / "step_last.log"),
        str(RESULTS / "sim_session.json"),
    ]
    return {
        "suite": "sim_log_triage",
        "version": 1,
        "overall_status": gate.get("overall_status") if isinstance(gate, dict) else None,
        "profile": gate.get("profile") if isinstance(gate, dict) else None,
        "layer_failures": layer_fails,
        "protocol_failures": proto_fail,
        "hardware_failures": hw_fail,
        "agent_hints": (gate.get("agent_hints") if isinstance(gate, dict) else None) or [],
        "soft_high_divergence": soft.get("high_divergence") or [],
        "soft_allowlist_unknown": (soft_al.get("unknown_high") or [])
        if isinstance(soft_al, dict)
        else [],
        "next_commands": (gate.get("next_commands") if isinstance(gate, dict) else None)
        or {
            "rerun": "python scripts/sim_rerun.py --from-last",
            "gate_quick": "python scripts/agent_gate.py --profile quick",
            "triage": "python scripts/sim_log_triage.py",
        },
        "log_paths": log_paths,
    }


def render_md(t: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Host SIL triage (R34)")
    lines.append("")
    lines.append(
        f"- **overall:** `{t.get('overall_status')}`  **profile:** `{t.get('profile')}`"
    )
    lines.append("")
    lines.append("## Layer failures")
    if not t.get("layer_failures"):
        lines.append("- (none)")
    else:
        for L in t["layer_failures"]:
            lines.append(
                f"- **{L.get('id')}** `{L.get('name')}` exit={L.get('exit_code')} — {L.get('detail')}"
            )
            if L.get("log_hint"):
                lines.append(f"  - log: `{L['log_hint']}`")
    lines.append("")
    lines.append("## Protocol failed cases")
    if not t.get("protocol_failures"):
        lines.append("- (none or no last_report)")
    else:
        for c in t["protocol_failures"]:
            lines.append(f"### `{c.get('name')}` ({c.get('kind')})")
            if c.get("detail"):
                lines.append(f"- detail: {c['detail']}")
            for bl in c.get("bad_lines") or []:
                lines.append(f"- send `{bl.get('line')}` → {bl.get('responses')}")
                if bl.get("detail"):
                    lines.append(f"  - {bl['detail']}")
    lines.append("")
    lines.append("## Hardware failed cases")
    if not t.get("hardware_failures"):
        lines.append("- (none or no last_hw_report)")
    else:
        for c in t["hardware_failures"]:
            lines.append(f"- **{c.get('name')}** — {c.get('detail')}")
    lines.append("")
    lines.append("## Soft / allowlist")
    high = t.get("soft_high_divergence") or []
    lines.append(f"- high_divergence: {high if high else '(none)'}")
    unk = t.get("soft_allowlist_unknown") or []
    if unk:
        lines.append(f"- allowlist unknown: {unk}")
    lines.append("")
    lines.append("## Agent hints")
    for h in t.get("agent_hints") or []:
        lines.append(f"- {h}")
    lines.append("")
    lines.append("## Next")
    nc = t.get("next_commands") or {}
    if isinstance(nc, dict):
        for k, v in nc.items():
            lines.append(f"- **{k}:** `{v}`")
    lines.append("")
    lines.append("## Log paths")
    for p in t.get("log_paths") or []:
        exists = Path(p).is_file()
        lines.append(f"- `{'OK' if exists else 'missing'}` {p}")
    lines.append("")
    lines.append(
        "_Host SIL ≠ paper/BT/OTA. Do not flash for parser issues until protocol/hardware pass._"
    )
    lines.append("")
    return "\n".join(lines)


def print_fail_slices(t: Dict[str, Any], max_cases: int = 6) -> None:
    """R35: compact stdout dump for red gates."""
    print("\n=== FAIL SLICES (R35) ===", flush=True)
    for L in (t.get("layer_failures") or [])[:8]:
        print(
            f"LAYER {L.get('id')}: {L.get('name')} exit={L.get('exit_code')} — {L.get('detail')}",
            flush=True,
        )
    for c in (t.get("protocol_failures") or [])[:max_cases]:
        print(f"PROTOCOL FAIL: {c.get('name')} ({c.get('kind')})", flush=True)
        if c.get("detail"):
            print(f"  detail: {c['detail']}", flush=True)
        for bl in (c.get("bad_lines") or [])[:3]:
            print(f"  send: {bl.get('line')!r}", flush=True)
            print(f"  got:  {bl.get('responses')}", flush=True)
    for c in (t.get("hardware_failures") or [])[:max_cases]:
        print(f"HARDWARE FAIL: {c.get('name')} — {c.get('detail')}", flush=True)
    print(f"TRIAGE: {TRIAGE_MD}", flush=True)
    print("=== END FAIL SLICES ===\n", flush=True)


def write_triage(t: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if t is None:
        t = build_triage()
    RESULTS.mkdir(parents=True, exist_ok=True)
    TRIAGE_JSON.write_text(
        json.dumps(t, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    TRIAGE_MD.write_text(render_md(t), encoding="utf-8")
    return t


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R34 host SIL log triage")
    ap.add_argument("--print-slices", action="store_true", help="also print R35 fail slices")
    ap.add_argument(
        "--fail-only-slices",
        action="store_true",
        help="print slices only if protocol/hw/layer failures exist",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    t = write_triage()
    print(f"wrote {TRIAGE_MD}")
    print(f"wrote {TRIAGE_JSON}")
    print(
        f"overall={t.get('overall_status')} "
        f"proto_fail={len(t.get('protocol_failures') or [])} "
        f"hw_fail={len(t.get('hardware_failures') or [])} "
        f"layers={len(t.get('layer_failures') or [])}"
    )
    has_fail = bool(
        t.get("layer_failures") or t.get("protocol_failures") or t.get("hardware_failures")
    )
    if args.print_slices or (args.fail_only_slices and has_fail):
        print_fail_slices(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
