#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-first host SIL gate for vibe coding (no burn/flash required).

PURPOSE
  AI agents (Kimi/Claude/Codex/Atom) should call this **proactively** after
  firmware/protocol/sim changes so bugs show up on the PC before USB flash.

DEFAULT
  profile=auto  — pick quick|standard from changed paths / env
  Always writes: results/agent_gate_last.json  (machine-readable)

PROFILES
  quick     protocol_sim only (~40s)     — G-code parse / error codes
  standard  protocol + hardware_sim      — motion/plant (default for code)
  deep      standard + full_release_smoke G1+G5 + unit tests
  firmware  standard + optional G0 pio if GRBL_ROOT (slow)

EXIT
  0 all hard layers pass
  1 one or more hard layers fail  → read report.failures + agent_hints
  2 tool/preflight missing (sim binary)
  3 invalid args

Does NOT claim product paper/BT/OTA. Those need hil_to_gate + evidence YAML.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
REPORT_PATH = RESULTS / "agent_gate_last.json"


@dataclass
class Layer:
    id: str
    name: str
    status: str  # pass|fail|skip
    exit_code: Optional[int] = None
    duration_s: float = 0.0
    detail: str = ""
    log_hint: str = ""


def _run(cmd: List[str], cwd: Optional[Path] = None) -> tuple[int, float]:
    print("AGENT_GATE_RUN:", " ".join(cmd), flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(cwd or FZ_ROOT), env=os.environ.copy())
    return proc.returncode, round(time.time() - t0, 2)


def _git_changed_paths(repo: Path) -> List[str]:
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        return []
    paths: List[str] = []
    for args in (
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "status", "-z", "--porcelain"],
    ):
        try:
            r = subprocess.run(
                args,
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0:
            continue
        if "-z" in args:
            # porcelain -z: status + path pairs roughly; split on \0
            for part in (r.stdout or "").split("\0"):
                part = part.strip()
                if len(part) > 3 and part[2:3] == " ":
                    paths.append(part[3:].replace("\\", "/"))
                elif part and not part.startswith("?"):
                    # untracked ?? path
                    if part.startswith("?? "):
                        paths.append(part[3:].replace("\\", "/"))
        else:
            for line in (r.stdout or "").splitlines():
                line = line.strip().replace("\\", "/")
                if line:
                    paths.append(line)
    # unique preserve order
    seen = set()
    out: List[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def classify_touch(paths: Sequence[str]) -> Dict[str, bool]:
    """Heuristic: what the agent changed."""
    flags = {
        "docs_only": True,
        "protocol_surface": False,
        "motion_planner": False,
        "product_custom": False,
        "web_only": False,
        "sim_harness": False,
        "any_code": False,
    }
    if not paths:
        flags["docs_only"] = False  # unknown → treat as code
        flags["any_code"] = True
        return flags

    code_ext = {".c", ".cpp", ".h", ".hpp", ".ino", ".py", ".nc", ".json"}
    web_ext = {".html", ".js", ".css", ".gz"}
    for raw in paths:
        p = raw.replace("\\", "/")
        low = p.lower()
        ext = Path(p).suffix.lower()
        if ext in code_ext or "/src/" in low or low.endswith(".ino"):
            flags["any_code"] = True
            flags["docs_only"] = False
        if ext in web_ext or "/embedded/" in low or "/www/" in low:
            flags["web_only"] = True
        if any(
            x in low
            for x in (
                "gcode",
                "protocol",
                "serial",
                "parser",
                "report.cpp",
                "settings",
            )
        ):
            flags["protocol_surface"] = True
            flags["any_code"] = True
            flags["docs_only"] = False
        if any(
            x in low
            for x in (
                "planner",
                "stepper",
                "motioncontrol",
                "limits",
                "jog",
                "spindle",
            )
        ):
            flags["motion_planner"] = True
            flags["any_code"] = True
            flags["docs_only"] = False
        if "custom/" in low or "paper" in low or "btstate" in low:
            flags["product_custom"] = True
            flags["any_code"] = True
            flags["docs_only"] = False
        if any(
            x in low
            for x in (
                "protocol_sim",
                "hardware_sim",
                "sim_common",
                "agent_gate",
                "win_full_sim",
            )
        ):
            flags["sim_harness"] = True
            flags["any_code"] = True
            flags["docs_only"] = False
        if ext in {".md", ".txt", ".csv"} and "/src/" not in low:
            pass
        elif ext not in web_ext and ext not in {".md", ".txt"}:
            flags["docs_only"] = False

    if flags["any_code"]:
        flags["docs_only"] = False
    # pure web without firmware src
    if flags["web_only"] and not flags["protocol_surface"] and not flags["motion_planner"]:
        if not any("/src/" in p.replace("\\", "/").lower() for p in paths):
            pass
    return flags


def pick_profile(
    explicit: str,
    grbl_root: Optional[Path],
    fz_paths: List[str],
    grbl_paths: List[str],
) -> str:
    if explicit != "auto":
        return explicit
    env = os.environ.get("AGENT_GATE_PROFILE", "").strip().lower()
    if env in ("quick", "standard", "deep", "firmware"):
        return env

    flags = classify_touch(list(fz_paths) + list(grbl_paths))
    if flags["docs_only"] and not flags["sim_harness"]:
        return "quick"
    if flags["sim_harness"]:
        return "standard"
    if flags["motion_planner"] or flags["product_custom"]:
        return "standard"
    if flags["protocol_surface"]:
        return "quick"
    if flags["any_code"]:
        return "standard"
    return "standard"


def _load_soft_div() -> Any:
    p = FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _failed_case_names(report_path: Path, limit: int = 8) -> List[str]:
    if not report_path.is_file():
        return []
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    names: List[str] = []
    # protocol_sim: list of CaseResult dicts
    if isinstance(data, list):
        for c in data:
            if isinstance(c, dict) and c.get("passed") is False:
                names.append(str(c.get("name") or "?"))
    elif isinstance(data, dict):
        for c in data.get("cases") or []:
            if isinstance(c, dict) and c.get("passed") is False:
                names.append(str(c.get("name") or "?"))
    return names[:limit]


def agent_hints_for_failures(layers: List[Layer]) -> List[str]:
    hints: List[str] = []
    for L in layers:
        if L.status != "fail":
            continue
        if L.id == "protocol":
            failed = _failed_case_names(FZ_ROOT / "protocol_sim" / "results" / "last_report.json")
            hints.append(
                "Read protocol_sim/results/last_report.json; fix G-code/error expectation "
                "or product parser if intentionally diverging (document divergence)."
            )
            if failed:
                hints.append("Failed protocol cases: " + ", ".join(failed))
            hints.append(
                "Re-run: python protocol_sim/run_regression.py --start-sim"
            )
        elif L.id == "hardware":
            failed = _failed_case_names(FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json")
            hints.append(
                "Read hardware_sim/results/last_hw_report.json; check MPos/plant/step logs."
            )
            if failed:
                hints.append("Failed hardware cases: " + ", ".join(failed))
            hints.append(
                "Re-run: python hardware_sim/run_hw_sim.py --start-sim"
            )
        elif L.id == "units":
            hints.append("Fix unit tests under sim_common/hardware_sim/hil/chip_sim.")
        elif L.id == "integrity":
            hints.append(
                "Integrity inject leaked false-green — harness/expect matching broken. "
                "Read protocol_sim/results/integrity_inject_last.json; "
                "re-run: python protocol_sim/run_regression.py --start-sim --integrity-inject"
            )
        elif L.id == "soft_allowlist":
            hints.append(
                "Soft allowlist failed — add match to protocol_sim/cases/soft/allowlist.yaml "
                "or reduce product soft divergence. See soft_allowlist_last.json"
            )
        elif L.id == "release_smoke":
            hints.append("full_release_smoke failed — open latest release/bundles/*/SUMMARY.md")
        elif L.id == "g0":
            hints.append(
                "G0 pio build failed — fix compile errors in GRBL_ROOT (test_drive)."
            )
        elif L.id == "preflight":
            hints.append(
                "grblHAL_sim missing — set GRBLHAL_SIM or restore vendor/grblhal_sim/bin"
            )
    if not hints:
        hints.append("No hard failures.")
    # soft divergence + allowlist (informational)
    soft_path = FZ_ROOT / "protocol_sim" / "results" / "soft_divergence.json"
    if soft_path.is_file():
        try:
            soft = json.loads(soft_path.read_text(encoding="utf-8"))
            high = soft.get("high_divergence") or []
            if high:
                hints.append(
                    "Soft product-sample divergence (not hard fail): "
                    + ", ".join(high)
                    + " — see protocol_sim/results/soft_divergence.json"
                )
            elif int(soft.get("total_err_lines") or 0) > 0:
                hints.append(
                    f"Soft streams had {soft.get('total_err_lines')} err lines "
                    "(informational; host SIL still green if hard passed)."
                )
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    al_path = FZ_ROOT / "protocol_sim" / "results" / "soft_allowlist_last.json"
    if al_path.is_file():
        try:
            al = json.loads(al_path.read_text(encoding="utf-8"))
            unk = al.get("unknown_high") or []
            if unk and al.get("passed") is False:
                hints.append(
                    "Soft allowlist UNKNOWN_HIGH: "
                    + ", ".join(str(x.get("name")) for x in unk[:6])
                    + " — edit cases/soft/allowlist.yaml"
                )
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    hints.append(
        "Host SIL ≠ product paper/BT. Do not claim G3b from this gate alone."
    )
    hints.append(
        "Fast rerun: python scripts/sim_rerun.py --from-last   "
        "or --protocol NAME --hardware NAME"
    )
    return hints


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Agent vibe-coding gate (PC host SIL, no flash)"
    )
    ap.add_argument(
        "--profile",
        default="auto",
        choices=("auto", "quick", "standard", "deep", "firmware"),
        help="auto picks from git changes; default for agents: auto",
    )
    ap.add_argument(
        "--grbl-root",
        type=Path,
        default=None,
        help="firmware tree for change detection / optional G0",
    )
    ap.add_argument(
        "--hw-fast",
        action="store_true",
        help="hardware_sim --fast (skip reliable plant hold)",
    )
    ap.add_argument(
        "--json-out",
        type=Path,
        default=REPORT_PATH,
        help="report path (default results/agent_gate_last.json)",
    )
    ap.add_argument(
        "--print-contract",
        action="store_true",
        help="print agent contract and exit 0",
    )
    ap.add_argument(
        "--no-shared-sim",
        action="store_true",
        help="R21 off: each layer spawns its own --start-sim (slower)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.print_contract:
        print(CONTRACT)
        return 0

    grbl = args.grbl_root or Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
    if not grbl.is_dir():
        grbl = None

    fz_paths = _git_changed_paths(FZ_ROOT)
    grbl_paths = _git_changed_paths(grbl) if grbl else []
    touch = classify_touch(list(fz_paths) + list(grbl_paths))
    profile = pick_profile(args.profile, grbl, fz_paths, grbl_paths)

    RESULTS.mkdir(parents=True, exist_ok=True)
    layers: List[Layer] = []
    t_all = time.time()

    print(f"AGENT_GATE profile={profile} grbl_root={grbl}", flush=True)
    print(f"AGENT_GATE touch={json.dumps(touch)}", flush=True)

    # preflight sim binary
    sys.path.insert(0, str(FZ_ROOT))
    try:
        from sim_common.find_sim import find_sim
    except ImportError:
        find_sim = None  # type: ignore

    sim = find_sim() if find_sim else None
    if not sim:
        layers.append(
            Layer(
                id="preflight",
                name="grblHAL_sim",
                status="fail",
                exit_code=2,
                detail="sim binary not found",
            )
        )
        return _finish(layers, profile, touch, grbl, args.json_out, 2, time.time() - t_all)

    layers.append(
        Layer(id="preflight", name="grblHAL_sim", status="pass", detail=str(sim))
    )

    # always: quick units for sim_common (cheap)
    code, dur = _run(
        [sys.executable, "-m", "unittest", "discover", "-s", "sim_common", "-p", "test_*.py", "-q"]
    )
    layers.append(
        Layer(
            id="units",
            name="sim_common_unittest",
            status="pass" if code == 0 else "fail",
            exit_code=code,
            duration_s=dur,
            log_hint="python -m unittest discover -s sim_common -q",
        )
    )

    # R21: one protocol-mode sim for integrity + protocol (hardware still own process)
    use_shared = not bool(getattr(args, "no_shared_sim", False))
    sess = None
    endpoint: List[str] = []
    stop_session = None  # type: ignore
    start_protocol_session = None  # type: ignore
    if use_shared:
        try:
            from sim_common.sim_session import (  # type: ignore
                start_protocol_session,
                stop_session,
            )
        except ImportError:
            start_protocol_session = None  # type: ignore
            stop_session = None  # type: ignore
            use_shared = False
        if use_shared and start_protocol_session is not None:
            try:
                t_sess = time.time()
                sess = start_protocol_session()
                endpoint = sess.endpoint_args()
                print(
                    f"AGENT_GATE shared_sim host={sess.host} port={sess.port} "
                    f"pid={sess.pid} boot={round(time.time() - t_sess, 2)}s",
                    flush=True,
                )
                layers.append(
                    Layer(
                        id="sim_session",
                        name="shared_protocol_sim",
                        status="pass",
                        duration_s=round(time.time() - t_sess, 2),
                        detail=f"{sess.host}:{sess.port}",
                    )
                )
            except Exception as exc:  # noqa: BLE001 — fall back to per-layer start
                print(f"AGENT_GATE: shared sim failed ({exc}); using --start-sim", flush=True)
                use_shared = False
                sess = None
                endpoint = []
                layers.append(
                    Layer(
                        id="sim_session",
                        name="shared_protocol_sim",
                        status="skip",
                        detail=f"fallback: {exc}",
                    )
                )
    else:
        layers.append(
            Layer(
                id="sim_session",
                name="shared_protocol_sim",
                status="skip",
                detail="--no-shared-sim",
            )
        )

    def _proto_base() -> List[str]:
        cmd = [
            sys.executable,
            str(FZ_ROOT / "protocol_sim" / "run_regression.py"),
        ]
        if endpoint:
            cmd.extend(endpoint)
        else:
            cmd.append("--start-sim")
        return cmd

    try:
        # R19 integrity inject: false-green packs must all go RED
        integ_cmd = _proto_base() + ["--integrity-inject"]
        code, dur = _run(integ_cmd)
        if code == 2:
            print("AGENT_GATE: integrity exit 2 — retry once after 1s", flush=True)
            time.sleep(1.0)
            code2, dur2 = _run(integ_cmd)
            code, dur = code2, round(dur + dur2, 2)
        layers.append(
            Layer(
                id="integrity",
                name="inject_false_green_must_red",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=dur,
                log_hint="protocol_sim/results/integrity_inject_last.json",
                detail="R19: harness must catch false-green expects",
            )
        )

        # protocol includes golden by default (R19)
        proto_cmd = _proto_base()
        if grbl is not None:
            proto_cmd.append("--include-repo-tests")
        code, dur = _run(proto_cmd)
        if code == 2:
            print("AGENT_GATE: protocol exit 2 — retry once after 1s", flush=True)
            time.sleep(1.0)
            code2, dur2 = _run(proto_cmd)
            code, dur = code2, round(dur + dur2, 2)
        layers.append(
            Layer(
                id="protocol",
                name="protocol_sim",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=dur,
                log_hint="protocol_sim/results/last_report.json + golden_last.json",
            )
        )
    finally:
        if sess is not None and stop_session is not None:
            print("AGENT_GATE: stopping shared protocol sim", flush=True)
            stop_session(sess)
            sess = None

    # R24: soft allowlist — unknown high_divergence is warn on quick/standard, fail on deep+
    soft_cmd = [
        sys.executable,
        str(FZ_ROOT / "scripts" / "soft_allowlist.py"),
    ]
    code, dur = _run(soft_cmd)
    soft_strict = profile in ("deep", "firmware")
    if code == 0:
        soft_status = "pass"
    elif soft_strict:
        soft_status = "fail"
    else:
        # keep gate green for vibe coding; surface via detail + hints
        soft_status = "pass"
    layers.append(
        Layer(
            id="soft_allowlist",
            name="soft_divergence_allowlist",
            status=soft_status,
            exit_code=code,
            duration_s=dur,
            log_hint="protocol_sim/results/soft_allowlist_last.json",
            detail=(
                "ok"
                if code == 0
                else (
                    "unknown high soft divergence (hard on deep/firmware)"
                    if soft_strict
                    else "WARN unknown high soft (not hard-fail on quick/standard)"
                )
            ),
        )
    )

    need_hw = profile in ("standard", "deep", "firmware")
    if need_hw:
        # hardware needs -s/-b step logs → own sim process (not shared)
        hw_cmd = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_hw_sim.py"),
            "--start-sim",
        ]
        if args.hw_fast:
            hw_cmd.append("--fast")
        code, dur = _run(hw_cmd)
        layers.append(
            Layer(
                id="hardware",
                name="hardware_sim",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=dur,
                log_hint="hardware_sim/results/last_hw_report.json",
            )
        )
    else:
        layers.append(
            Layer(id="hardware", name="hardware_sim", status="skip", detail="profile=quick")
        )

    if profile in ("deep", "firmware"):
        code, dur = _run(
            [sys.executable, str(FZ_ROOT / "scripts" / "full_release_smoke.py")]
        )
        layers.append(
            Layer(
                id="release_smoke",
                name="full_release_smoke",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=dur,
                log_hint="release/bundles/*/SUMMARY.md",
            )
        )
    else:
        layers.append(
            Layer(
                id="release_smoke",
                name="full_release_smoke",
                status="skip",
                detail="not in profile",
            )
        )

    if profile == "firmware" and grbl is not None:
        env = os.environ.copy()
        env["GRBL_ROOT"] = str(grbl)
        print("AGENT_GATE_RUN: full_release_smoke --with-g0", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [
                sys.executable,
                str(FZ_ROOT / "scripts" / "full_release_smoke.py"),
                "--with-g0",
                "--g0-mode",
                "test_drive",
            ],
            cwd=str(FZ_ROOT),
            env=env,
        )
        layers.append(
            Layer(
                id="g0",
                name="pio_test_drive_build",
                status="pass" if proc.returncode == 0 else "fail",
                exit_code=proc.returncode,
                duration_s=round(time.time() - t0, 2),
                detail="optional compile gate",
            )
        )
    else:
        layers.append(
            Layer(
                id="g0",
                name="pio_test_drive_build",
                status="skip",
                detail="profile!=firmware or no GRBL_ROOT",
            )
        )

    hard_fail = any(x.status == "fail" for x in layers)
    overall = 1 if hard_fail else 0
    return _finish(
        layers, profile, touch, grbl, args.json_out, overall, time.time() - t_all
    )


def _finish(
    layers: List[Layer],
    profile: str,
    touch: Dict[str, bool],
    grbl: Optional[Path],
    json_out: Path,
    overall: int,
    duration_s: float,
) -> int:
    failures = [asdict(x) for x in layers if x.status == "fail"]
    hints = agent_hints_for_failures(layers)
    report: Dict[str, Any] = {
        "suite": "agent_gate",
        "version": 1,
        "fidelity": "host_sil_for_agents_not_product_hil",
        "profile": profile,
        "overall_exit": overall,
        "overall_status": "pass" if overall == 0 else "fail",
        "duration_s": round(duration_s, 2),
        "grbl_root": str(grbl) if grbl else None,
        "touch": touch,
        "layers": [asdict(x) for x in layers],
        "failures": failures,
        "agent_hints": hints,
        "claims_forbidden": [
            "paper_path_verified",
            "bt_verified",
            "wifi_ota_verified",
            "product_flash_ok",
            "chip_qemu_app_ok",
        ],
        "next_commands": {
            "recheck_quick": "python scripts/agent_gate.py --profile quick",
            "recheck_standard": "python scripts/agent_gate.py --profile standard",
            "no_shared_sim": "python scripts/agent_gate.py --profile quick --no-shared-sim",
            "protocol_only": "python protocol_sim/run_regression.py --start-sim",
            "golden_only": "python protocol_sim/run_regression.py --start-sim --golden",
            "integrity_inject": (
                "python protocol_sim/run_regression.py --start-sim --integrity-inject"
            ),
            "golden_record": (
                "python scripts/golden_record.py --from-last --kinds fail --only NAME"
            ),
            "soft_allowlist": "python scripts/soft_allowlist.py",
            "hardware_only": "python hardware_sim/run_hw_sim.py --start-sim",
            "rerun_failed": "python scripts/sim_rerun.py --from-last",
            "list_failures": "python scripts/sim_rerun.py --list",
            "soft_divergence": "protocol_sim/results/soft_divergence.json",
            "with_board": "python scripts/hil_to_gate.py --port COMx",
        },
        "soft_divergence": _load_soft_div(),
        "report_path": str(
            json_out if json_out.is_absolute() else FZ_ROOT / json_out
        ),
    }
    out = json_out if json_out.is_absolute() else FZ_ROOT / json_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== agent_gate ===", flush=True)
    for x in layers:
        print(
            f"  [{x.status.upper():4}] {x.id:14} {x.name}"
            + (f" exit={x.exit_code}" if x.exit_code is not None else "")
            + (f" {x.duration_s}s" if x.duration_s else "")
            + (f" — {x.detail}" if x.detail else ""),
            flush=True,
        )
    print(f"overall: {report['overall_status']} exit={overall} profile={profile}", flush=True)
    print(f"report: {out}", flush=True)
    print("AGENT_HINTS:", flush=True)
    for h in hints:
        print(f"  - {h}", flush=True)
    if overall == 0:
        print(
            "AGENT_NEXT: host SIL green — safe to continue coding; "
            "still need HIL for paper/BT before ship.",
            flush=True,
        )
    else:
        print(
            "AGENT_NEXT: fix failures above using agent_hints; "
            "do NOT flash board until protocol/hardware pass "
            "(unless debugging silicon-only).",
            flush=True,
        )
    return overall


CONTRACT = """
# Agent contract: PC sim before flash (fz agent_gate)

WHEN (must run, no waiting for human):
  - After editing Grbl_Esp32 GCode/Protocol/Planner/Stepper/Limits/Serial/Settings
  - After editing fz protocol_sim / hardware_sim / sim_common
  - Before claiming "fixed" / "ready to flash" / "LGTM for motion/parser"

COMMAND (from any cwd if FZ_ROOT set):
  cd /d D:\\Users\\zhugu\\fz
  set GRBL_ROOT=D:\\Users\\Grbl_Esp32
  python scripts/agent_gate.py
  # or: python scripts/agent_gate.py --profile quick|standard|deep|firmware

READ on failure:
  D:\\Users\\zhugu\\fz\\results\\agent_gate_last.json
  → failures[], agent_hints[], next_commands

DO NOT:
  - Skip gate and burn firmware to "see if it works" for parser/motion bugs
  - Claim paper/BT/OTA from agent_gate green
  - Add new sim engines under Grbl_Esp32 tree (live in fz)

PROFILES:
  auto      — default; git-touch heuristic
  quick     — protocol only (fast parse/error loop)
  standard  — protocol + hardware_sim (vibe coding default)
  deep      — + full_release_smoke
  firmware  — + pio test_drive G0 (slow)

LOOP / HONESTY (EDA-inspired):
  python scripts/agent_loop.py --profile standard
  python scripts/release_honesty.py --require-agent-gate --allow-pending-hil
  → results/release_honesty_last.json  (KiCad-like pre-fab checklist machine check)
"""


if __name__ == "__main__":
    raise SystemExit(main())
