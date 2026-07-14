#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R38: agent observability surface — always-on findings + next actions.

After every host SIL run, agents need a single machine-readable object that
answers: what happened, what is suspicious, what to improve, what to run next.

Writes:
  results/agent_observe_last.json
  results/agent_observe_last.md

Does not re-run sim. Reads gate/triage/protocol/soft artifacts only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
OUT_JSON = RESULTS / "agent_observe_last.json"
OUT_MD = RESULTS / "agent_observe_last.md"


def _read_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _finding(
    severity: str,
    category: str,
    title: str,
    detail: str = "",
    action: str = "",
    refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "severity": severity,  # hard | soft | info | optimize
        "category": category,
        "title": title,
        "detail": detail,
        "action": action,
        "refs": refs or [],
    }


def build_observe() -> Dict[str, Any]:
    gate = _read_json(RESULTS / "agent_gate_last.json") or {}
    soft = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json") or {}
    soft_al = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_allowlist_last.json") or {}
    golden = _read_json(FZ_ROOT / "protocol_sim" / "results" / "golden_last.json") or {}
    schema = _read_json(FZ_ROOT / "protocol_sim" / "results" / "case_schema_last.json") or {}
    last_proto = _read_json(FZ_ROOT / "protocol_sim" / "results" / "last_report.json")
    triage = _read_json(RESULTS / "triage_last.json") or {}
    integrity = _read_json(
        FZ_ROOT / "protocol_sim" / "results" / "integrity_inject_last.json"
    ) or {}

    findings: List[Dict[str, Any]] = []
    overall = gate.get("overall_status") if isinstance(gate, dict) else None
    profile = gate.get("profile") if isinstance(gate, dict) else None

    # --- hard failures ---
    for L in (gate.get("failures") if isinstance(gate, dict) else None) or []:
        if not isinstance(L, dict):
            continue
        findings.append(
            _finding(
                "hard",
                "layer_fail",
                f"layer {L.get('id')} failed",
                detail=str(L.get("detail") or L.get("name") or ""),
                action="python scripts/sim_rerun.py --from-last",
                refs=[str(L.get("log_hint") or ""), str(RESULTS / "triage_last.md")],
            )
        )

    for c in (triage.get("protocol_failures") if isinstance(triage, dict) else None) or []:
        if not isinstance(c, dict):
            continue
        bl = (c.get("bad_lines") or [{}])[0]
        findings.append(
            _finding(
                "hard",
                "protocol_case",
                f"protocol case failed: {c.get('name')}",
                detail=str(c.get("detail") or bl.get("detail") or ""),
                action=f"python scripts/sim_rerun.py --protocol {c.get('name')}",
                refs=["protocol_sim/results/last_report.json"],
            )
        )

    for c in (triage.get("hardware_failures") if isinstance(triage, dict) else None) or []:
        if not isinstance(c, dict):
            continue
        findings.append(
            _finding(
                "hard",
                "hardware_case",
                f"hardware case failed: {c.get('name')}",
                detail=str(c.get("detail") or ""),
                action="python hardware_sim/run_hw_sim.py --start-sim",
                refs=["hardware_sim/results/last_hw_report.json"],
            )
        )

    # --- soft / product divergence (always interesting) ---
    high = list(soft.get("high_divergence") or []) if isinstance(soft, dict) else []
    for name in high:
        findings.append(
            _finding(
                "soft",
                "product_divergence",
                f"soft high divergence: {name}",
                detail="Product sample vs grblHAL host SIL — not hard gate fail",
                action="see protocol_sim/results/soft_divergence.json; fix product or allowlist",
                refs=["protocol_sim/results/soft_divergence.json", "protocol_sim/cases/soft/allowlist.yaml"],
            )
        )
    total_err = int(soft.get("total_err_lines") or 0) if isinstance(soft, dict) else 0
    if total_err and not high:
        findings.append(
            _finding(
                "soft",
                "product_divergence",
                f"soft streams had {total_err} err lines",
                detail="Informational; hard suite may still be green",
                action="python scripts/sim_log_triage.py",
                refs=["protocol_sim/results/soft_divergence.json"],
            )
        )

    unk = list(soft_al.get("unknown_high") or []) if isinstance(soft_al, dict) else []
    if unk:
        findings.append(
            _finding(
                "soft",
                "allowlist",
                "soft allowlist has UNKNOWN_HIGH",
                detail=json.dumps(unk, ensure_ascii=False)[:400],
                action="edit protocol_sim/cases/soft/allowlist.yaml or reduce soft errors",
                refs=["protocol_sim/results/soft_allowlist_last.json"],
            )
        )

    # --- green-path health / optimize ---
    if overall == "pass":
        findings.append(
            _finding(
                "info",
                "gate",
                "host SIL hard layers green",
                detail=f"profile={profile}",
                action="continue coding; still need HIL for paper/BT before ship",
                refs=[str(RESULTS / "agent_gate_last.json")],
            )
        )

    if isinstance(integrity, dict) and integrity.get("passed") is True:
        findings.append(
            _finding(
                "info",
                "integrity",
                "false-green inject packs all red (harness OK)",
                detail=f"n={integrity.get('n')} red={integrity.get('n_red_as_expected')}",
                action="",
                refs=["protocol_sim/results/integrity_inject_last.json"],
            )
        )
    elif isinstance(integrity, dict) and integrity.get("passed") is False:
        findings.append(
            _finding(
                "hard",
                "integrity",
                "integrity inject leaked false green",
                detail=str(integrity.get("n_leaked_false_green")),
                action="python protocol_sim/run_regression.py --start-sim --integrity-inject",
                refs=["protocol_sim/results/integrity_inject_last.json"],
            )
        )

    if isinstance(golden, dict) and golden.get("n"):
        n_fail = int(golden.get("n_fail") or 0)
        findings.append(
            _finding(
                "hard" if n_fail else "info",
                "golden",
                f"golden pack {golden.get('n')} cases fail={n_fail}",
                detail="",
                action="python protocol_sim/run_regression.py --start-sim --golden"
                if n_fail
                else "",
                refs=["protocol_sim/results/golden_last.json"],
            )
        )

    if isinstance(schema, dict) and schema.get("n_files"):
        n_err = int(schema.get("n_errors") or 0)
        findings.append(
            _finding(
                "hard" if n_err else "info",
                "case_schema",
                f"protocol JSON cases files={schema.get('n_files')} errors={n_err}",
                detail=str(schema.get("by_dir") or ""),
                action="python protocol_sim/validate_cases.py",
                refs=["protocol_sim/results/case_schema_last.json"],
            )
        )

    # protocol hard count from last_report
    if isinstance(last_proto, list):
        hard = [c for c in last_proto if isinstance(c, dict) and c.get("kind") != "soft"]
        soft_c = [c for c in last_proto if isinstance(c, dict) and c.get("kind") == "soft"]
        hard_fail = [c for c in hard if c.get("passed") is False]
        findings.append(
            _finding(
                "info",
                "protocol_stats",
                f"last protocol hard {len(hard) - len(hard_fail)}/{len(hard)} soft={len(soft_c)}",
                detail="",
                action="",
                refs=["protocol_sim/results/last_report.json"],
            )
        )

    # optimize suggestions (always, non-blocking)
    findings.append(
        _finding(
            "optimize",
            "loop",
            "prefer sim_rerun over full gate when iterating one case",
            detail="saves minutes on Windows",
            action="python scripts/sim_rerun.py --from-last",
            refs=["scripts/sim_rerun.py"],
        )
    )
    if profile == "quick" and overall == "pass":
        findings.append(
            _finding(
                "optimize",
                "coverage",
                "quick is green — run standard before claiming motion fixed",
                detail="hardware_sim skipped on quick",
                action="python scripts/agent_gate.py --profile standard",
                refs=["docs/AGENT_VIBE_CODING.md"],
            )
        )
    findings.append(
        _finding(
            "optimize",
            "honesty",
            "before ship language, run release_honesty",
            detail="blocks stale gate and forbidden claims",
            action=(
                "python scripts/release_honesty.py --require-agent-gate --allow-pending-hil"
            ),
            refs=["scripts/release_honesty.py"],
        )
    )
    findings.append(
        _finding(
            "info",
            "hil_boundary",
            "host SIL cannot prove paper/BT/OTA",
            detail="with board: hil_to_gate --port + hil_logs",
            action="python scripts/hil_to_gate.py --port COMx",
            refs=["results/hil_log_index.md", "hil/README.md"],
        )
    )

    # ranked next actions
    next_actions: List[str] = []
    for f in findings:
        if f["severity"] == "hard" and f.get("action"):
            next_actions.append(f["action"])
    for f in findings:
        if f["severity"] == "soft" and f.get("action") and f["action"] not in next_actions:
            next_actions.append(f["action"])
    for f in findings:
        if f["severity"] == "optimize" and f.get("action") and f["action"] not in next_actions:
            next_actions.append(f["action"])
    if not next_actions:
        next_actions.append("python scripts/agent_gate.py --profile quick")

    hard_n = sum(1 for f in findings if f["severity"] == "hard")
    soft_n = sum(1 for f in findings if f["severity"] == "soft")

    return {
        "suite": "agent_observe",
        "version": 1,
        "overall_status": overall,
        "profile": profile,
        "summary": {
            "hard_findings": hard_n,
            "soft_findings": soft_n,
            "info_findings": sum(1 for f in findings if f["severity"] == "info"),
            "optimize_findings": sum(1 for f in findings if f["severity"] == "optimize"),
            "agent_should_block_done_claim": hard_n > 0 or overall == "fail",
        },
        "findings": findings,
        "next_actions": next_actions[:12],
        "read_first": [
            str(RESULTS / "agent_observe_last.md"),
            str(RESULTS / "triage_last.md"),
            str(RESULTS / "agent_gate_last.json"),
        ],
        "claims_forbidden": (gate.get("claims_forbidden") if isinstance(gate, dict) else None)
        or [
            "paper_path_verified",
            "bt_verified",
            "wifi_ota_verified",
            "product_flash_ok",
        ],
    }


def render_md(obs: Dict[str, Any]) -> str:
    lines = [
        "# Agent observe (R38)",
        "",
        f"- **overall:** `{obs.get('overall_status')}` **profile:** `{obs.get('profile')}`",
        f"- **hard/soft/info/optimize:** {obs.get('summary')}",
        "",
        "## Findings (severity-ordered)",
        "",
    ]
    order = {"hard": 0, "soft": 1, "info": 2, "optimize": 3}
    findings = sorted(
        obs.get("findings") or [],
        key=lambda f: order.get(str(f.get("severity")), 9),
    )
    for f in findings:
        lines.append(f"### [{f.get('severity')}] {f.get('title')}")
        if f.get("detail"):
            lines.append(f"- detail: {f['detail']}")
        if f.get("action"):
            lines.append(f"- action: `{f['action']}`")
        if f.get("refs"):
            lines.append(f"- refs: {', '.join(f'`{r}`' for r in f['refs'] if r)}")
        lines.append("")
    lines.append("## Next actions")
    for a in obs.get("next_actions") or []:
        lines.append(f"1. `{a}`")
    lines.append("")
    lines.append("## Read first")
    for p in obs.get("read_first") or []:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("_Observable loop: gate → observe → fix → sim_rerun → gate. Host SIL ≠ HIL._")
    lines.append("")
    return "\n".join(lines)


def write_observe(obs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if obs is None:
        obs = build_observe()
    RESULTS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(obs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    OUT_MD.write_text(render_md(obs), encoding="utf-8")
    return obs


def print_observe_brief(obs: Dict[str, Any]) -> None:
    s = obs.get("summary") or {}
    print("\n=== AGENT_OBSERVE (R38) ===", flush=True)
    print(
        f"overall={obs.get('overall_status')} profile={obs.get('profile')} "
        f"hard={s.get('hard_findings')} soft={s.get('soft_findings')} "
        f"block_done_claim={s.get('agent_should_block_done_claim')}",
        flush=True,
    )
    for f in (obs.get("findings") or [])[:8]:
        if f.get("severity") in ("hard", "soft"):
            print(f"  [{f.get('severity')}] {f.get('title')}", flush=True)
    print("NEXT:", flush=True)
    for a in (obs.get("next_actions") or [])[:5]:
        print(f"  → {a}", flush=True)
    print(f"READ: {OUT_MD}", flush=True)
    print("=== END AGENT_OBSERVE ===\n", flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="R38 agent observe surface")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    obs = write_observe()
    if not args.quiet:
        print_observe_brief(obs)
        print(f"wrote {OUT_MD}")
        print(f"wrote {OUT_JSON}")
    # exit 1 if hard findings so agents can chain; soft-only still 0
    if (obs.get("summary") or {}).get("hard_findings", 0) > 0:
        return 1
    if obs.get("overall_status") == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
