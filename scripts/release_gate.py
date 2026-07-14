#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-release defect gate orchestrator (fz).

Exit codes (design):
  0 — all hard layers pass (or explicitly waived)
  1 — at least one hard layer failed
  2 — scope/config error (e.g. paper_path without G3 evidence)
  3 — required hard layer not run (unknown)

Does NOT claim product firmware binary equivalence to grblHAL_sim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


FZ_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCOPE = FZ_ROOT / "release" / "release_scope.example.yaml"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_scope(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Minimal YAML subset (key: value / nested features)
    return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parse the example scope format without PyYAML."""
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Any]] = [(-1, root)]
    pending_key: Optional[str] = None
    pending_indent = 0

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            item = line[2:].strip().strip('"').strip("'")
            if pending_key is not None and isinstance(parent, dict):
                lst = parent.setdefault(pending_key, [])
                if not isinstance(lst, list):
                    lst = []
                    parent[pending_key] = lst
                # value may be bare or key: val on list — we only support bare strings
                if item and not item.endswith(":") and ":" not in item:
                    lst.append(_coerce(item))
                elif ":" in item:
                    # skip complex list maps for minimal parser
                    pass
            continue

        if ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest == "" or rest == "|" or rest == ">":
                # nested map or list follows
                if isinstance(parent, dict):
                    # peek: if next content is list, use list; default dict
                    parent[key] = {}
                    stack.append((indent, parent[key]))
                    pending_key = key
                    pending_indent = indent
            else:
                if isinstance(parent, dict):
                    parent[key] = _coerce(rest)
                pending_key = None
    # Fix features/machines that should be lists: re-parse machines/blockers with second pass
    return _fix_lists(text, root)


def _fix_lists(text: str, root: Dict[str, Any]) -> Dict[str, Any]:
    """Second pass for list keys machines, blockers_open, waivers."""
    for list_key in ("machines", "blockers_open", "waivers"):
        items: List[Any] = []
        in_section = False
        base_indent = None
        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            s = raw.strip()
            if s.startswith(list_key + ":"):
                in_section = True
                base_indent = indent
                rest = s.split(":", 1)[1].strip()
                if rest and rest not in ("", "[]"):
                    # inline empty
                    pass
                continue
            if in_section:
                if base_indent is not None and indent <= base_indent and not s.startswith("-"):
                    in_section = False
                    continue
                if s.startswith("- "):
                    items.append(_coerce(s[2:].strip()))
        if items or list_key in root:
            root[list_key] = items if items else root.get(list_key, [])
            if isinstance(root[list_key], dict):
                root[list_key] = items
    # features should stay dict
    if not isinstance(root.get("features"), dict):
        root["features"] = root.get("features") or {}
    return root


def _coerce(val: str) -> Any:
    v = val.strip().strip('"').strip("'")
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    if v.lower() in ("null", "~", ""):
        return None
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_coerce(x.strip()) for x in inner.split(",")]
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v


def _git_sha(cwd: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_g1_protocol(bundle: Path, port: int) -> Dict[str, Any]:
    """Run protocol_sim with --start-sim; copy last_report.json."""
    script = FZ_ROOT / "protocol_sim" / "run_regression.py"
    env = os.environ.copy()
    sim = FZ_ROOT / "vendor" / "grblhal_sim" / "bin" / "grblHAL_sim.exe"
    if sim.is_file():
        env.setdefault("GRBLHAL_SIM", str(sim))
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(script), "--start-sim", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(FZ_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    report_src = FZ_ROOT / "protocol_sim" / "results" / "last_report.json"
    report: Any = None
    if report_src.is_file():
        shutil.copy2(report_src, bundle / "g1_protocol_cases.json")
        try:
            report = json.loads(report_src.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = None
    status = "pass" if proc.returncode == 0 else ("fail" if proc.returncode == 1 else "error")
    result = {
        "layer": "G1",
        "name": "protocol_sim",
        "status": status,
        "exit_code": proc.returncode,
        "duration_s": round(time.time() - t0, 2),
        "engine": "grblHAL_sim",
        "engine_note": "grblHAL_sim is NOT the product Grbl_Esp32 binary",
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
        "cases_file": "g1_protocol_cases.json" if report_src.is_file() else None,
    }
    _write_json(bundle / "g1_protocol.json", result)
    return result


def run_g1_hardware_sim(bundle: Path, port: int) -> Dict[str, Any]:
    """Optional hardware_sim suite; skip if runner missing."""
    script = FZ_ROOT / "hardware_sim" / "run_hw_sim.py"
    if not script.is_file():
        result = {
            "layer": "G1",
            "name": "hardware_sim",
            "status": "skipped_not_implemented",
            "note": "run_hw_sim.py not present",
        }
        _write_json(bundle / "g1_hardware_sim.json", result)
        return result
    env = os.environ.copy()
    sim = FZ_ROOT / "vendor" / "grblhal_sim" / "bin" / "grblHAL_sim.exe"
    if sim.is_file():
        env.setdefault("GRBLHAL_SIM", str(sim))
    t0 = time.time()
    # Use different port to avoid clash if protocol left something (should be clean)
    hw_port = port + 1
    # --time-factor 1: plant feed-hold needs Run state (community grbl realtime)
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--start-sim",
            "--port",
            str(hw_port),
            "--time-factor",
            "1",
        ],
        cwd=str(FZ_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    status = "pass" if proc.returncode == 0 else "fail"
    result = {
        "layer": "G1",
        "name": "hardware_sim",
        "status": status,
        "exit_code": proc.returncode,
        "duration_s": round(time.time() - t0, 2),
        "engine": "grblHAL_sim",
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }
    _write_json(bundle / "g1_hardware_sim.json", result)
    return result


def run_g0_build(bundle: Path, grbl_root: Optional[Path], machines: Sequence[str]) -> Dict[str, Any]:
    """Compile product firmware with PlatformIO when GRBL_ROOT is set."""
    if grbl_root is None or not grbl_root.is_dir():
        result = {
            "layer": "G0",
            "status": "skipped_no_grbl_root",
            "note": "Set GRBL_ROOT to run build gate",
        }
        _write_json(bundle / "g0_build.json", result)
        return result

    pio = shutil.which("pio") or shutil.which("platformio")
    if not pio:
        result = {
            "layer": "G0",
            "status": "fail",
            "note": "pio/platformio not on PATH",
        }
        _write_json(bundle / "g0_build.json", result)
        return result

    builds: List[Dict[str, Any]] = []
    overall = "pass"
    # Always try default release; optional MACHINE_FILENAME for listed machines
    targets: List[Tuple[str, Dict[str, str]]] = [("default_release", {})]
    for m in machines:
        if m and m != "default":
            targets.append((m, {"PLATFORMIO_BUILD_FLAGS": f"-DMACHINE_FILENAME={m}.h"}))

    for name, extra_env in targets:
        env = os.environ.copy()
        env.update(extra_env)
        t0 = time.time()
        proc = subprocess.run(
            [pio, "run", "-e", "release"],
            cwd=str(grbl_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
        st = "pass" if proc.returncode == 0 else "fail"
        if st == "fail":
            overall = "fail"
        builds.append(
            {
                "target": name,
                "status": st,
                "exit_code": proc.returncode,
                "duration_s": round(time.time() - t0, 2),
                "stderr_tail": (proc.stderr or "")[-1500:],
                "stdout_tail": (proc.stdout or "")[-1500:],
            }
        )
        # For speed: if default fails, still record others optional — continue

    result = {
        "layer": "G0",
        "status": overall,
        "grbl_root": str(grbl_root),
        "builds": builds,
    }
    _write_json(bundle / "g0_build.json", result)
    return result


def run_g2_placeholder(bundle: Path, scope: Dict[str, Any]) -> Dict[str, Any]:
    features = scope.get("features") or {}
    if not features.get("cloud_qwen"):
        result = {
            "layer": "G2",
            "status": "skipped_not_in_scope",
            "note": "features.cloud_qwen is false",
        }
    else:
        result = {
            "layer": "G2",
            "status": "unknown",
            "note": "Cloud contract suite not wired yet — treat as required if shipping cloud",
        }
    _write_json(bundle / "g2_contracts.json", result)
    return result


def run_g3_status(bundle: Path, scope: Dict[str, Any], g3_evidence: Optional[Path]) -> Dict[str, Any]:
    features = scope.get("features") or {}
    needs_product = bool(features.get("paper_path") or features.get("bluetooth"))
    if g3_evidence and g3_evidence.is_file():
        dest = bundle / "g3_acceptance_checklist.md"
        shutil.copy2(g3_evidence, dest)
        result = {
            "layer": "G3",
            "status": "pass",
            "note": "Operator-supplied evidence copied; gate does not re-verify content",
            "evidence": str(dest.name),
        }
    elif needs_product:
        result = {
            "layer": "G3",
            "status": "unknown",
            "note": "features require product HIL (paper/bt) but --g3-evidence not provided",
            "required_for": [k for k in ("paper_path", "bluetooth") if features.get(k)],
        }
    else:
        result = {
            "layer": "G3",
            "status": "skipped_not_in_scope",
            "note": "No paper_path/bluetooth in scope; silicon still recommended",
        }
    _write_json(bundle / "g3_hil.json", result)
    return result


def run_g4_placeholder(bundle: Path, scope: Dict[str, Any]) -> Dict[str, Any]:
    features = scope.get("features") or {}
    if features.get("ota"):
        result = {
            "layer": "G4",
            "status": "unknown",
            "note": "OTA in scope but automated G4 not implemented",
        }
    else:
        result = {
            "layer": "G4",
            "status": "skipped_no_ota",
            "note": "features.ota is false",
        }
    _write_json(bundle / "g4_ota.json", result)
    return result


def run_g5_meta(bundle: Path, scope: Dict[str, Any], grbl_root: Optional[Path]) -> Dict[str, Any]:
    sim = FZ_ROOT / "vendor" / "grblhal_sim" / "bin" / "grblHAL_sim.exe"
    result = {
        "layer": "G5",
        "status": "pass",
        "generated_at": _utc_now(),
        "fz_git_sha": _git_sha(FZ_ROOT),
        "grbl_git_sha": _git_sha(grbl_root) if grbl_root else scope.get("grbl_git_sha") or "unknown",
        "sim_engine": "grblHAL_sim",
        "sim_binary_sha256_16": _file_sha256(sim),
        "scope_version": scope.get("version"),
        "features": scope.get("features"),
        "blockers_open": scope.get("blockers_open") or [],
        "waivers": scope.get("waivers") or [],
        "warnings": [],
    }
    if result["blockers_open"]:
        result["status"] = "fail"
        result["warnings"].append("blockers_open must be empty to ship")
    # Soft security notes
    result["security_notes"] = [
        "Product authentication may be weak/cleartext — document residual risk in SIGN_OFF",
        "Do not commit real Wi-Fi credentials",
    ]
    _write_json(bundle / "g5_security_meta.json", result)
    return result


def _layer_hard_status(layer: Dict[str, Any], scope: Dict[str, Any]) -> str:
    return str(layer.get("status", "unknown"))


def decide_exit(layers: Dict[str, Dict[str, Any]], scope: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Returns (exit_code, reasons).
    """
    reasons: List[str] = []
    features = scope.get("features") or {}

    # Config errors
    g3 = layers.get("G3", {})
    if g3.get("status") == "unknown" and (
        features.get("paper_path") or features.get("bluetooth")
    ):
        reasons.append("G3 required by scope but no evidence (unknown)")
        return 3, reasons

    g2 = layers.get("G2", {})
    if features.get("cloud_qwen") and g2.get("status") == "unknown":
        reasons.append("G2 cloud in scope but contracts not run (unknown)")
        return 3, reasons

    g4 = layers.get("G4", {})
    if features.get("ota") and g4.get("status") == "unknown":
        reasons.append("G4 OTA in scope but not run (unknown)")
        return 3, reasons

    # Failures
    for name, layer in layers.items():
        st = layer.get("status")
        if st == "fail":
            reasons.append(f"{name} failed")
        if st == "error":
            reasons.append(f"{name} error")
    if any(layers.get(n, {}).get("status") in ("fail", "error") for n in layers):
        # G0 skipped is ok
        hard_fail = False
        for n, layer in layers.items():
            st = layer.get("status")
            if st in ("fail", "error"):
                if n == "G0" and st == "fail":
                    hard_fail = True
                elif n != "G0":
                    hard_fail = True
                elif n == "G0":
                    hard_fail = True
        if hard_fail:
            return 1, reasons

    if layers.get("G5", {}).get("status") == "fail":
        return 1, reasons or ["G5 blockers_open nonempty"]

    # G1 protocol must pass for any release gate success
    if layers.get("G1_protocol", {}).get("status") != "pass":
        reasons.append("G1 protocol_sim did not pass")
        return 1, reasons

    # hardware_sim fail is hard when present
    hw = layers.get("G1_hardware_sim", {})
    if hw.get("status") == "fail":
        reasons.append("G1 hardware_sim failed")
        return 1, reasons

    return 0, reasons or ["all hard checks ok or skipped_in_scope"]


def write_summary(
    bundle: Path,
    scope: Dict[str, Any],
    layers: Dict[str, Dict[str, Any]],
    exit_code: int,
    reasons: Sequence[str],
) -> None:
    lines = [
        f"# Release gate SUMMARY — {scope.get('version', 'unknown')}",
        "",
        f"- generated_at: `{_utc_now()}`",
        f"- exit_code: **{exit_code}**",
        f"- reasons: {', '.join(reasons)}",
        "",
        "## Engine honesty",
        "",
        "- `grblHAL_sim` / G1 **≠** product Grbl_Esp32 firmware binary.",
        "- Product paper/BT/I2S require **G3** evidence, not G1 alone.",
        "",
        "## Layers",
        "",
        "| Layer | Status |",
        "|-------|--------|",
    ]
    for key in ("G0", "G1_protocol", "G1_hardware_sim", "G2", "G3", "G4", "G5"):
        layer = layers.get(key, {})
        lines.append(f"| {key} | `{layer.get('status', 'missing')}` |")
    lines.extend(
        [
            "",
            "## Taxonomy reminder (manual)",
            "",
            "Map open issues to D1–D11 in pre-release design; Unknown untested = Blocker.",
            "",
            "## Unproven / residual",
            "",
        ]
    )
    unproven: List[str] = []
    for key, layer in layers.items():
        st = layer.get("status", "")
        if st.startswith("skipped") or st == "unknown":
            unproven.append(f"- **{key}**: {st} — {layer.get('note', '')}")
    if not unproven:
        unproven.append("- (none listed; still verify G3 for product ships)")
    lines.extend(unproven)
    lines.extend(["", "## Next", "", "- Fill SIGN_OFF.md only if exit_code==0 and residual risk accepted.", ""])
    (bundle / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    sign = (FZ_ROOT / "release" / "SIGN_OFF.template.md").read_text(encoding="utf-8")
    (bundle / "SIGN_OFF.md").write_text(
        sign.replace("<version>", str(scope.get("version", "unknown"))),
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="fz pre-release defect gate")
    ap.add_argument(
        "--scope",
        type=Path,
        default=DEFAULT_SCOPE,
        help="release scope YAML",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="bundle output directory (default release/bundles/<version>-<ts>)",
    )
    ap.add_argument(
        "--only",
        type=str,
        default="",
        help="comma list: G0,G1,G2,G3,G4,G5 (default all)",
    )
    ap.add_argument(
        "--skip-g0",
        action="store_true",
        help="skip firmware build even if GRBL_ROOT set",
    )
    ap.add_argument(
        "--g3-evidence",
        type=Path,
        default=None,
        help="path to filled ACCEPTANCE checklist or HIL report",
    )
    ap.add_argument("--port", type=int, default=7681, help="TCP port for protocol_sim")
    ap.add_argument(
        "--allow-unknown",
        action="store_true",
        help="do not exit 3 on unknown layers (dev only; not for ship)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    scope_path = args.scope if args.scope.is_absolute() else FZ_ROOT / args.scope
    if not scope_path.is_file():
        print(f"ERROR: scope not found: {scope_path}", file=sys.stderr)
        return 2

    scope = _load_scope(scope_path)
    version = str(scope.get("version") or "dev")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle = args.out
    if bundle is None:
        bundle = FZ_ROOT / "release" / "bundles" / f"{version}-{ts}"
    elif not bundle.is_absolute():
        bundle = FZ_ROOT / bundle
    bundle.mkdir(parents=True, exist_ok=True)
    shutil.copy2(scope_path, bundle / "scope.yaml")

    only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
    if not only:
        only = {"G0", "G1", "G2", "G3", "G4", "G5"}

    grbl_env = os.environ.get("GRBL_ROOT", "").strip()
    grbl_root = Path(grbl_env) if grbl_env else None
    machines = scope.get("machines") or []
    if not isinstance(machines, list):
        machines = []

    layers: Dict[str, Dict[str, Any]] = {}

    if "G0" in only and not args.skip_g0:
        print("=== G0 build ===")
        layers["G0"] = run_g0_build(bundle, grbl_root, [str(m) for m in machines])
    elif "G0" in only:
        layers["G0"] = {
            "layer": "G0",
            "status": "skipped_flag",
            "note": "--skip-g0",
        }
        _write_json(bundle / "g0_build.json", layers["G0"])

    if "G1" in only:
        print("=== G1 protocol_sim ===")
        layers["G1_protocol"] = run_g1_protocol(bundle, args.port)
        print("=== G1 hardware_sim ===")
        layers["G1_hardware_sim"] = run_g1_hardware_sim(bundle, args.port)

    if "G2" in only:
        print("=== G2 contracts ===")
        layers["G2"] = run_g2_placeholder(bundle, scope)

    if "G3" in only:
        print("=== G3 HIL/evidence ===")
        g3_path = args.g3_evidence
        if g3_path and not g3_path.is_absolute():
            g3_path = Path.cwd() / g3_path
        layers["G3"] = run_g3_status(bundle, scope, g3_path)

    if "G4" in only:
        print("=== G4 OTA ===")
        layers["G4"] = run_g4_placeholder(bundle, scope)

    if "G5" in only:
        print("=== G5 meta ===")
        layers["G5"] = run_g5_meta(bundle, scope, grbl_root)

    exit_code, reasons = decide_exit(layers, scope)
    if args.allow_unknown and exit_code == 3:
        print("WARN: --allow-unknown overrides exit 3 → 0 for dev", file=sys.stderr)
        exit_code = 0
        reasons = list(reasons) + ["allow_unknown"]

    write_summary(bundle, scope, layers, exit_code, reasons)
    print("")
    print(f"bundle: {bundle}")
    print(f"exit_code: {exit_code} ({'; '.join(reasons)})")
    print(f"SUMMARY: {bundle / 'SUMMARY.md'}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
