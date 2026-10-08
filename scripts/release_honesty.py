#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Release honesty check — EDA-inspired (KiCad ERC/DRC before fab).

Does NOT flash boards. Combines:
  - last agent_gate / SIL artifacts
  - soft_divergence warnings
  - structured G3/G4 evidence and current source identity vs scope flags
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
import subprocess
import sys
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
OUT_PATH = RESULTS / "release_honesty_last.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_report import atomic_write_json
from release_inputs import load_scope, validate_signoff_evidence

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
    except (OSError, ValueError, UnicodeError):
        return None


def _file_age_hours(path: Path) -> Optional[float]:
    try:
        return (time.time() - path.stat().st_mtime) / 3600.0
    except OSError:
        return None


def _scan_claims(text: str) -> List[str]:
    hits: List[str] = []
    for rx, label in FORBIDDEN:
        if rx.search(text or ""):
            hits.append(label)
    return hits


def _git_head(repo: Optional[Path]) -> Optional[str]:
    if repo is None or not Path(repo).exists():
        return None
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (r.stdout or "").strip() or None if r.returncode == 0 else None


def _git_dirty(repo: Optional[Path]) -> Optional[bool]:
    if repo is None or not Path(repo).exists():
        return None
    try:
        result = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                                cwd=repo, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return bool(result.stdout.strip()) if result.returncode == 0 else None


def check_code_identity(
    gate: Dict[str, Any],
    current: Dict[str, Optional[str]],
    scope_raw: str = "",
    sign_off: bool = False,
    current_dirty: Optional[Dict[str, Optional[bool]]] = None,
) -> Dict[str, List[str]]:
    """门禁报告必须绑在当前代码上（必修#2）。

    仅靠文件 mtime 判新鲜度时，代码改过之后窗口内的旧 pass 仍可签核。
    这里要求报告自带 sha 且与当前 HEAD 相符；scope 若声明了 sha 也一并比对。
    """
    blockers: List[str] = []
    warnings: List[str] = []
    notes: List[str] = []

    identity = gate.get("code_identity")
    if not isinstance(identity, dict):
        blockers.append(
            "agent_gate report has no code_identity (旧格式) — 无法把 SIL 证据绑到代码版本，"
            "重跑 agent_gate 生成带 sha 的报告"
        )
        return {"blockers": blockers, "warnings": warnings, "notes": notes}

    current_dirty = current_dirty or {}
    for repo_key, label in (("fz", "fz"), ("grbl", "GRBL_ROOT")):
        dirty_now = current_dirty.get(repo_key)
        if sign_off and dirty_now is not False:
            blockers.append(f"{label}: 当前工作树脏或状态未知，不能签核")
        elif not sign_off and dirty_now is not False:
            warnings.append(f"{label}: 当前工作树脏或状态未知 [dev 允许]")
        recorded = (identity.get(repo_key) or {}) if isinstance(identity.get(repo_key), dict) else {}
        sha = recorded.get("sha")
        now = current.get(repo_key)
        if sha is None and now is None:
            (blockers if sign_off else notes).append(f"{label}: 无 git 身份（仓缺失或非 git 树）")
            continue
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
            blockers.append(f"{label}: 门禁报告缺 sha，但当前树有 HEAD {str(now)[:12]} — 重跑门禁")
            continue
        if now is None:
            (blockers if sign_off else warnings).append(f"{label}: 当前取不到 HEAD，无法比对报告 sha {str(sha)[:12]}")
            continue
        if sha != now:
            blockers.append(
                f"{label}: 门禁报告跑在 {sha[:12]}，当前 HEAD 是 {now[:12]} — "
                "代码已变动，旧 pass 不能用于签核，重跑 agent_gate"
            )
            continue
        notes.append(f"{label}: sha {sha[:12]} 与当前 HEAD 相符")
        if recorded.get("dirty") is not False:
            msg = f"{label}: 门禁运行时工作树脏（sha {sha[:12]} 不能完整描述被测代码）"
            if sign_off:
                blockers.append(msg)
            else:
                warnings.append(msg + " [dev 允许]")

    # scope已按结构解析；保留旧函数调用中的文本SHA校验兼容面。
    for key, repo_key in (("fz_git_sha", "fz"), ("grbl_git_sha", "grbl")):
        match = re.search(rf'^\s*{key}\s*:\s*["\']?([0-9a-fA-F]{{7,40}})', scope_raw, re.M)
        if not match:
            continue
        recorded_identity = identity.get(repo_key)
        recorded = recorded_identity.get("sha") if isinstance(recorded_identity, dict) else None
        if not isinstance(recorded, str):
            recorded = ""
        if not recorded or not recorded.lower().startswith(match.group(1).lower()):
            blockers.append(f"scope 声明 {key} 与门禁报告不符")

    return {"blockers": blockers, "warnings": warnings, "notes": notes}


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
        help="validated G3 evidence YAML/JSON with source identity and log files",
    )
    ap.add_argument(
        "--g4-evidence",
        type=Path,
        default=None,
        help="validated G4 evidence YAML/JSON with source identity and log files",
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
    if not isinstance(gate, dict):
        gate = None
    age_h = _file_age_hours(gate_path)
    if not math.isfinite(args.max_age_hours) or args.max_age_hours <= 0:
        blockers.append("max-age-hours必须为有限正数")
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
        if gate.get("run_state", "completed") != "completed":
            blockers.append("agent_gate本轮未完成，不能使用其结果")
        for layer in gate.get("layers") or []:
            if not isinstance(layer, dict):
                blockers.append("agent_gate层格式错误")
                continue
            status, name = layer.get("status"), str(layer.get("id") or "unknown")
            if status == "fail":
                if layer.get("blocking") is False:
                    warnings.append(f"{name}: 非阻断失败；启动或检查仍未验证")
                else:
                    blockers.append(f"agent_gate层{name}失败")
            elif status == "skip":
                warnings.append(f"{name}: 已跳过；检查未验证")

    soft = _read_json(FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json") or {}
    if not isinstance(soft, dict):
        soft = {}
    high = list(soft.get("high_divergence") or [])
    if high:
        warnings.append(
            "soft high divergence (not auto-block): " + ", ".join(high)
        )
    total_err = int(soft.get("total_err_lines") or 0)
    if total_err:
        notes.append(f"soft total_err_lines={total_err}")

    paper = bt = ota = False
    scope_raw = ""
    scope_data = {}
    scope_path = args.scope
    if scope_path is None:
        candidate = FZ_ROOT / "release/scopes/pre-release-min.yaml"
        scope_path = candidate if candidate.is_file() else None
    elif not scope_path.is_absolute():
        scope_path = FZ_ROOT / scope_path
    if scope_path is not None:
        try:
            scope_data = load_scope(scope_path)
            features = scope_data["features"]
            paper, bt, ota = (features[key] for key in ("paper_path", "bluetooth", "ota"))
            scope_raw = "\n".join(f"{key}: {scope_data[key]}" for key in ("fz_git_sha", "grbl_git_sha") if key in scope_data)
            notes.append(f"scope={scope_path.name} paper={paper} bt={bt} ota={ota}")
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as error:
            blockers.append(f"scope无效：{type(error).__name__}: {error}")

    # 报告↔代码绑定：mtime 窗口挡不住「代码改了但仍在 24h/168h 内」的旧 pass。
    identity_blocked = False
    if gate is not None:
        grbl_root = os.environ.get("GRBL_ROOT") or gate.get("grbl_root")
        found = check_code_identity(
            gate,
            {
                "fz": _git_head(FZ_ROOT),
                "grbl": _git_head(Path(grbl_root)) if grbl_root else None,
            },
            scope_raw=scope_raw,
            sign_off=args.scope is not None,
            current_dirty={"fz": _git_dirty(FZ_ROOT),
                           "grbl": _git_dirty(Path(grbl_root)) if grbl_root else None},
        )
        blockers.extend(found["blockers"])
        warnings.extend(found["warnings"])
        notes.extend(found["notes"])
        identity_blocked = bool(found["blockers"])

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
    evidence_reports = {}
    identities = (gate or {}).get("code_identity")
    product_identity = identities.get("grbl") if isinstance(identities, dict) else {}
    if not isinstance(product_identity, dict):
        product_identity = {}
    for kind, required, path in (("g3", paper or bt, g3), ("g4", ota, g4)):
        if not required:
            continue
        valid, detail = (False, {"status": "unknown", "errors": ["未提供证据文件"]})
        if path is not None:
            valid, detail = validate_signoff_evidence(path, scope_data["features"], kind,
                                                       FZ_ROOT, product_identity.get("sha"))
        evidence_reports[kind] = detail
        if not valid:
            hil_ok = False
            message = f"{kind}验收未通过：" + "; ".join(detail.get("errors", []))
            (warnings if args.allow_pending_hil else blockers).append(message)

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
    if not sil_ok or blockers:
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
        "agent_gate_run_id": (gate or {}).get("run_id"),
        "agent_gate_generated_at": (gate or {}).get("generated_at"),
        "agent_gate_code_identity": (gate or {}).get("code_identity"),
        "code_identity_ok": (gate is not None and not identity_blocked),
        "evidence": evidence_reports,
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
    atomic_write_json(out, report)

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

    if args.strict and gate is None:
        return 2
    if verdict == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
