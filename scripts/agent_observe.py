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


def _is_allowlisted(name: str, allowed_names: set[str]) -> bool:
    normalized = name.lower()
    return any(
        normalized == candidate or normalized.endswith(candidate) or candidate.endswith(normalized)
        for candidate in allowed_names
        if candidate
    )


def _paper_interaction_finding(report: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(report, dict) or report.get("status") != "fail":
        return None
    minimal = report.get("minimal_failure")
    detail = json.dumps(minimal, ensure_ascii=False, sort_keys=True) if isinstance(minimal, dict) else "no minimal failure recorded"
    return _finding(
        "hard",
        "paper_interactions",
        "paper interaction safety property failed",
        detail=detail,
        action="python hardware_sim/run_paper_plant_interactions.py",
        refs=["hardware_sim/results/paper_plant_interactions.json"],
    )


def _paper_contract_finding(report: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(report, dict) or report.get("status") != "fail":
        return None
    violations = report.get("violations") if isinstance(report.get("violations"), list) else []
    return _finding(
        "hard",
        "paper_contract",
        "paper firmware/Plant contract drifted",
        detail=json.dumps(violations[:5], ensure_ascii=False, sort_keys=True),
        action="python hardware_sim/run_paper_firmware_contract.py",
        refs=["hardware_sim/results/paper_firmware_contract.json", "hardware_sim/paper_firmware_contract.json"],
    )


def _paper_transient_finding(report: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(report, dict) or report.get("status") != "fail":
        return None
    failures = [case for case in report.get("cases", []) if isinstance(case, dict) and not case.get("passed")]
    return _finding(
        "hard",
        "paper_transients",
        "paper transient recovery property failed",
        detail=json.dumps(failures[:3], ensure_ascii=False, sort_keys=True),
        action="python hardware_sim/run_paper_transient_campaign.py",
        refs=["hardware_sim/results/paper_plant_transients.json"],
    )


def _machine_pin_findings(report: Any) -> List[Dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    if report.get("status") == "fail":
        errors = report.get("errors") if isinstance(report.get("errors"), list) else []
        actions = report.get("next_actions") if isinstance(report.get("next_actions"), list) else []
        detail = {"errors": errors[:5], "remediation": actions[:3]}
        return [
            _finding(
                "hard",
                "machine_pin_erc",
                "machine pin ERC failed closed",
                detail=json.dumps(detail, ensure_ascii=False, sort_keys=True),
                action="python hardware_sim/run_machine_pin_erc.py",
                refs=["hardware_sim/results/machine_pin_erc.json", "hardware_sim/machine_pin_contract.json"],
            )
        ]
    if report.get("status") == "pass":
        return [
            _finding(
                "info",
                "machine_pin_erc",
                "machine pin contract coverage",
                detail=f"{coverage.get('contracted_pin_macros', 0)}/{coverage.get('resolvable_pin_macros', 0)} macros ({coverage.get('percent', 0)}%); waivers={len(report.get('waivers') or [])}",
                refs=["hardware_sim/results/machine_pin_erc.json"],
            )
        ]
    return []


def _machine_pin_mutation_findings(report: Any) -> List[Dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    score = report.get("mutation_score") if isinstance(report.get("mutation_score"), dict) else {}
    if report.get("status") == "fail":
        return [_finding("hard", "machine_pin_mutations", "firmware pin checker missed an injected defect", detail=json.dumps(report.get("failures", [])[:5], ensure_ascii=False, sort_keys=True), action="python hardware_sim/run_machine_pin_mutation_campaign.py", refs=["hardware_sim/results/machine_pin_mutations.json"])]
    if report.get("status") == "pass":
        return [_finding("info", "machine_pin_mutations", "firmware pin checker mutation score", detail=f"killed {score.get('killed', 0)}/{score.get('total', 0)} temporary pre-flash defects; valid baseline passed", refs=["hardware_sim/results/machine_pin_mutations.json"])]
    return []


def _wokwi_startup_findings(report: Any, layer_status: Optional[str]) -> List[Dict[str, Any]]:
    if layer_status == "skip" or not isinstance(report, dict):
        return []
    if report.get("status") == "pass":
        startup = report.get("startup") if isinstance(report.get("startup"), dict) else {}
        return [_finding("info", "wokwi_startup", "Wokwi ESP32 startup reached firmware ready marker", detail=f"ready={startup.get('ready_hits', [])}; boots={startup.get('boot_count', 0)}", refs=["results/wokwi/wokwi_smoke_report.json", "results/wokwi/serial.log"])]
    if report.get("cloud_error") == "unauthorized":
        return [_finding("hard", "wokwi_startup", "Wokwi cloud authentication failed", detail="WOKWI_CLI_TOKEN was rejected before firmware startup", action="refresh the GitHub/user WOKWI_CLI_TOKEN and rerun", refs=["results/wokwi/wokwi_smoke_report.json"])]
    startup = report.get("startup") if isinstance(report.get("startup"), dict) else {}
    return [_finding("hard", "wokwi_startup", "ESP32 cloud startup did not initialize cleanly", detail=json.dumps(startup.get("fatal_events", [])[:8], ensure_ascii=False, sort_keys=True), action="inspect results/wokwi/serial.log and rerun chip_sim/run_wokwi_smoke.py", refs=["results/wokwi/wokwi_smoke_report.json", "results/wokwi/serial.log"])]


def _fail_stems_without_golden() -> List[str]:
    """R39: fail cases that lack a matching golden_* contract (coverage gap)."""
    fail_dir = FZ_ROOT / "protocol_sim" / "cases" / "fail"
    gold_dir = FZ_ROOT / "protocol_sim" / "cases" / "golden"
    if not fail_dir.is_dir():
        return []
    gold_text = " ".join(p.stem.lower() for p in gold_dir.glob("*.json")) if gold_dir.is_dir() else ""
    missing: List[str] = []
    for p in sorted(fail_dir.glob("*.json")):
        stem = p.stem.lower()
        # match if golden name contains stem tokens or reverse
        tokens = [t for t in stem.replace("-", "_").split("_") if len(t) > 2]
        hit = stem in gold_text or any(t in gold_text for t in tokens[:3])
        # also check JSON name field loosely
        if not hit:
            try:
                nm = str(json.loads(p.read_text(encoding="utf-8")).get("name") or "").lower()
            except (OSError, json.JSONDecodeError):
                nm = ""
            if nm and (nm in gold_text or any(t in gold_text for t in nm.replace("-", "_").split("_") if len(t) > 3)):
                hit = True
        if not hit:
            missing.append(p.name)
    return missing


def build_observe() -> Dict[str, Any]:
    gate = _read_json(RESULTS / "agent_gate_last.json") or {}
    gate_layers = {str(layer.get("id")): str(layer.get("status")) for layer in (gate.get("layers") if isinstance(gate, dict) else None) or [] if isinstance(layer, dict)}
    soft = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json") or {}
    soft_al = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_allowlist_last.json") or {}
    golden = _read_json(FZ_ROOT / "protocol_sim" / "results" / "golden_last.json") or {}
    schema = _read_json(FZ_ROOT / "protocol_sim" / "results" / "case_schema_last.json") or {}
    last_proto = _read_json(FZ_ROOT / "protocol_sim" / "results" / "last_report.json")
    native_cov = _read_json(FZ_ROOT / "native_sim" / "results" / "coverage_summary.json") or {}
    paper_interactions = _read_json(FZ_ROOT / "hardware_sim" / "results" / "paper_plant_interactions.json") or {}
    paper_contract = _read_json(FZ_ROOT / "hardware_sim" / "results" / "paper_firmware_contract.json") or {}
    machine_pin_erc = _read_json(FZ_ROOT / "hardware_sim" / "results" / "machine_pin_erc.json") or {}
    machine_pin_mutations = _read_json(FZ_ROOT / "hardware_sim" / "results" / "machine_pin_mutations.json") or {}
    wokwi_startup = _read_json(FZ_ROOT / "results" / "wokwi" / "wokwi_smoke_report.json") or {}
    paper_transients = _read_json(FZ_ROOT / "hardware_sim" / "results" / "paper_plant_transients.json") or {}
    triage = _read_json(RESULTS / "triage_last.json") or {}
    integrity = _read_json(
        FZ_ROOT / "protocol_sim" / "results" / "integrity_inject_last.json"
    ) or {}

    findings: List[Dict[str, Any]] = []
    overall = gate.get("overall_status") if isinstance(gate, dict) else None
    profile = gate.get("profile") if isinstance(gate, dict) else None
    touch = gate.get("touch") if isinstance(gate, dict) else {}
    if not isinstance(touch, dict):
        touch = {}
    duration_s = gate.get("duration_s") if isinstance(gate, dict) else None

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

    paper_interaction_finding = _paper_interaction_finding(paper_interactions)
    if paper_interaction_finding is not None:
        findings.append(paper_interaction_finding)
    paper_contract_finding = _paper_contract_finding(paper_contract)
    if paper_contract_finding is not None:
        findings.append(paper_contract_finding)
    paper_transient_finding = _paper_transient_finding(paper_transients)
    if paper_transient_finding is not None:
        findings.append(paper_transient_finding)
    findings.extend(_machine_pin_findings(machine_pin_erc))
    findings.extend(_machine_pin_mutation_findings(machine_pin_mutations))
    findings.extend(_wokwi_startup_findings(wokwi_startup, gate_layers.get("wokwi_startup")))

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
    allowed_high = list(soft_al.get("allowed_high") or []) if isinstance(soft_al, dict) else []
    allowed_names = {str(item.get("name") or item.get("allow_match") or "").lower() for item in allowed_high if isinstance(item, dict)}

    for name in high:
        severity = "info" if _is_allowlisted(str(name), allowed_names) else "soft"
        findings.append(
            _finding(
                severity,
                "product_divergence",
                f"allowlisted soft divergence: {name}" if severity == "info" else f"soft high divergence: {name}",
                detail="Product sample vs grblHAL host SIL — not hard gate fail",
                action=(
                    "read docs/PRODUCT_SOFT_DIVERGENCE.md (R42 A/C); "
                    "do not gut M62/parser only for sim; see soft_divergence.json"
                ),
                refs=[
                    "docs/PRODUCT_SOFT_DIVERGENCE.md",
                    "protocol_sim/results/soft_divergence.json",
                    "protocol_sim/cases/soft/allowlist.yaml",
                ],
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
                action="docs/PRODUCT_SOFT_DIVERGENCE.md + python scripts/sim_log_triage.py",
                refs=["docs/PRODUCT_SOFT_DIVERGENCE.md", "protocol_sim/results/soft_divergence.json"],
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

    # R40: per-file soft sample radar (even when not high_divergence)
    soft_files = list(soft.get("files") or []) if isinstance(soft, dict) else []
    for sf in soft_files:
        if not isinstance(sf, dict):
            continue
        name = str(sf.get("name") or "")
        n_ok = int(sf.get("ok_lines") or 0)
        n_err = int(sf.get("err_lines") or 0)
        total = n_ok + n_err
        ratio = (n_err / total) if total else 0.0
        if n_err <= 0:
            findings.append(
                _finding(
                    "info",
                    "soft_sample",
                    f"soft sample clean: {name}",
                    detail=f"ok_lines={n_ok}",
                    action="",
                    refs=["protocol_sim/results/soft_divergence.json"],
                )
            )
            continue
        # extract first error codes from detail if present
        detail = str(sf.get("detail") or "")
        sev = "soft" if ratio >= 0.3 or name in high else "info"
        if _is_allowlisted(name, allowed_names):
            sev = "info"
        findings.append(
            _finding(
                sev,
                "soft_sample",
                f"soft sample errs: {name} err={n_err}/{total} ratio={ratio:.0%}",
                detail=detail[:300],
                action=(
                    "document product divergence or add hard fail if grblHAL should reject"
                    if sev == "soft"
                    else ""
                ),
                refs=["protocol_sim/results/soft_divergence.json", "protocol_sim/cases/soft/"],
            )
        )

    # R40: hardware_sim last report summary (if present)
    hw_rep = _read_json(FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json")
    if isinstance(hw_rep, dict) and hw_rep.get("cases") is not None:
        cases = [c for c in (hw_rep.get("cases") or []) if isinstance(c, dict)]
        n_pass = sum(1 for c in cases if c.get("passed") is True)
        n_fail = sum(1 for c in cases if c.get("passed") is False)
        step_log = hw_rep.get("step_log") or ""
        findings.append(
            _finding(
                "hard" if n_fail else "info",
                "hardware_stats",
                f"last hardware_sim cases {n_pass}/{len(cases)} fail={n_fail}",
                detail=f"engine={hw_rep.get('engine')} step_log={step_log}",
                action="python hardware_sim/run_hw_sim.py --start-sim" if n_fail else "",
                refs=[
                    "hardware_sim/results/last_hw_report.json",
                    str(step_log) if step_log else "",
                ],
            )
        )
        if profile == "quick" and cases:
            findings.append(
                _finding(
                    "info",
                    "hardware_stale_hint",
                    "hardware report exists but profile=quick did not re-run hardware",
                    detail="last_hw_report may be from an older standard run",
                    action="python scripts/agent_gate.py --profile standard",
                    refs=["hardware_sim/results/last_hw_report.json"],
                )
            )
    elif profile in ("standard", "deep", "firmware"):
        findings.append(
            _finding(
                "soft",
                "hardware_missing",
                "no hardware_sim last_hw_report after non-quick profile",
                detail="expected after standard/deep/firmware",
                action="python hardware_sim/run_hw_sim.py --start-sim",
                refs=["hardware_sim/"],
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

    if isinstance(native_cov, dict) and native_cov.get("status") in ("pass", "skip"):
        files = native_cov.get("files") if isinstance(native_cov.get("files"), dict) else {}
        if native_cov.get("status") == "skip":
            findings.append(
                _finding(
                    "optimize",
                    "native_coverage",
                    "native product coverage skipped",
                    detail=str(native_cov.get("stderr") or "coverage tools unavailable"),
                    action="install LLVM llvm-profdata/llvm-cov or run on Windows LLVM host",
                    refs=["native_sim/results/coverage_summary.json"],
                )
            )
        elif files:
            details = []
            low = []
            for name, item in sorted(files.items()):
                if not isinstance(item, dict):
                    continue
                pct = item.get("lines_percent")
                funcs = item.get("functions_percent")
                pct_text = f"{pct:.2f}" if isinstance(pct, (int, float)) else str(pct)
                funcs_text = f"{funcs:.2f}" if isinstance(funcs, (int, float)) else str(funcs)
                details.append(f"{name} lines={pct_text}% funcs={funcs_text}%")
                if isinstance(pct, (int, float)) and pct < 90.0:
                    low.append(f"{name}={pct}%")
            findings.append(
                _finding(
                    "info" if not low else "optimize",
                    "native_coverage",
                    "native product core coverage",
                    detail="; ".join(details),
                    action="add native fuzz/unit cases for low-coverage branches" if low else "",
                    refs=["native_sim/results/coverage_summary.json"],
                )
            )

    # --- R39: touch / layer skips / golden coverage gaps ---
    if touch.get("motion_planner") and profile == "quick":
        findings.append(
            _finding(
                "soft",
                "touch_profile",
                "git touch suggests motion/planner but profile=quick",
                detail=str(touch),
                action="python scripts/agent_gate.py --profile standard",
                refs=["results/agent_gate_last.json"],
            )
        )
    if touch.get("product_custom") and overall == "pass":
        findings.append(
            _finding(
                "soft",
                "touch_hil",
                "product custom/paper/BT paths touched — host SIL cannot close HIL",
                detail=str(touch),
                action="python scripts/hil_to_gate.py --port COMx  # or honesty --allow-pending-hil",
                refs=["docs/AGENT_VIBE_CODING.md", "hil/README.md"],
            )
        )
    if touch.get("protocol_surface") and overall == "pass":
        findings.append(
            _finding(
                "info",
                "touch",
                "protocol surface touched — keep golden/fail packs green",
                detail="rerun after parser edits",
                action="python scripts/agent_gate.py --profile quick",
                refs=["protocol_sim/cases/"],
            )
        )

    skipped = []
    if isinstance(gate, dict):
        for L in gate.get("layers") or []:
            if isinstance(L, dict) and L.get("status") == "skip":
                skipped.append(str(L.get("id") or L.get("name")))
    if skipped:
        findings.append(
            _finding(
                "info",
                "layers_skipped",
                f"skipped layers: {', '.join(skipped)}",
                detail="not a failure — know what was not exercised",
                action="python scripts/agent_gate.py --profile standard"
                if "hardware" in skipped
                else "",
                refs=["results/agent_gate_last.json"],
            )
        )

    if isinstance(duration_s, (int, float)) and duration_s > 180:
        findings.append(
            _finding(
                "optimize",
                "perf",
                f"gate took {duration_s:.0f}s — prefer sim_rerun for single-case fixes",
                detail="full quick can exceed 2min with large case packs",
                action="python scripts/sim_rerun.py --from-last",
                refs=["scripts/sim_rerun.py"],
            )
        )

    missing_gold = _fail_stems_without_golden()
    if missing_gold:
        findings.append(
            _finding(
                "optimize",
                "golden_coverage",
                f"{len(missing_gold)} fail case(s) without clear golden twin",
                detail=", ".join(missing_gold[:8])
                + ("…" if len(missing_gold) > 8 else ""),
                action=(
                    "python scripts/golden_record.py --from-case protocol_sim/cases/fail/NAME.json"
                ),
                refs=["scripts/golden_record.py", "protocol_sim/cases/fail/"],
            )
        )

    hil_logs = FZ_ROOT / "results" / "hil_logs"
    hil_n = len(list(hil_logs.glob("*.log"))) if hil_logs.is_dir() else 0
    if hil_n == 0:
        findings.append(
            _finding(
                "info",
                "hil_logs",
                "no HIL serial archives yet (results/hil_logs empty)",
                detail="expected when developing without a board",
                action="python scripts/hil_to_gate.py --port COMx  # when board available",
                refs=["hil/README.md"],
            )
        )
    else:
        findings.append(
            _finding(
                "info",
                "hil_logs",
                f"HIL serial archives present: {hil_n} log file(s)",
                detail="use for g3 evidence paths",
                action="results/hil_log_index.md",
                refs=["results/hil_log_index.md"],
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
            "optimize",
            "observe",
            "re-run observe after manual case edits without full gate",
            detail="cheap signal refresh",
            action="python scripts/agent_observe.py",
            refs=["scripts/agent_observe.py"],
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
        "version": 3,
        "overall_status": overall,
        "profile": profile,
        "touch": touch,
        "duration_s": duration_s,
        "summary": {
            "hard_findings": hard_n,
            "soft_findings": soft_n,
            "info_findings": sum(1 for f in findings if f["severity"] == "info"),
            "optimize_findings": sum(1 for f in findings if f["severity"] == "optimize"),
            "agent_should_block_done_claim": hard_n > 0 or overall == "fail",
            "agent_should_prefer_standard": bool(
                touch.get("motion_planner") or touch.get("product_custom")
            )
            and profile == "quick",
            "fail_without_golden": missing_gold[:20] if missing_gold else [],
            "soft_files_with_errors": [
                str(sf.get("name"))
                for sf in soft_files
                if isinstance(sf, dict) and int(sf.get("err_lines") or 0) > 0
            ],
            "hardware_cases_in_last_report": (
                len(hw_rep.get("cases") or [])
                if isinstance(hw_rep, dict)
                else 0
            ),
            "machine_pin_contract_coverage_percent": (
                (machine_pin_erc.get("coverage") or {}).get("percent")
                if isinstance(machine_pin_erc, dict)
                else None
            ),
            "machine_pin_mutation_score": (machine_pin_mutations.get("mutation_score") if isinstance(machine_pin_mutations, dict) else None),
            "wokwi_startup_status": (wokwi_startup.get("status") if gate_layers.get("wokwi_startup") != "skip" and isinstance(wokwi_startup, dict) else None),
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
