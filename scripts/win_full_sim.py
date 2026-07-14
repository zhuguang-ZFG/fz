#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows host full-stack SIL (not silicon / not product paper-BT).

Community anchors:
  - grblHAL/Simulator: -p TCP, -s/-b step/block logs, -t time factor, validator
  - Espressif QEMU / Wokwi / Renode: optional chip-level (chip_sim probe)
  - ioSender/linux.do-style desktop CNC: no board → sim for protocol + planner
  - Golioth/HIL: real board is separate path (hil_to_gate.py)
  Catalog: docs/specs/2026-07-14-opensource-sim-fusion-catalog.md

Layers (default L0–L4; L5 optional):
  L0 preflight  — vendor sim binary + runtime DLLs
  L1 protocol   — protocol_sim/run_regression.py --start-sim
  L2 hardware   — hardware_sim/run_hw_sim.py --start-sim
  L3 unit       — step_oracle + hil logic unittest (no board)
  L4 honesty    — product_stubs gaps recorded in report (never auto-pass)
  L5 chip_probe — inventory qemu/wokwi/renode (soft unless --require-chip-tool)

Exit codes:
  0 all selected layers ok
  1 one or more layers failed
  2 preflight / missing sim
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


FZ_ROOT = Path(__file__).resolve().parent.parent
VENDOR_BIN = FZ_ROOT / "vendor" / "grblhal_sim" / "bin"
RESULTS = FZ_ROOT / "results"


@dataclass
class LayerResult:
    id: str
    name: str
    status: str  # pass | fail | skip
    exit_code: Optional[int] = None
    detail: str = ""
    duration_s: float = 0.0
    artifacts: List[str] = field(default_factory=list)


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.3)
        s.connect((host, port))
        s.close()
        return False  # something listening
    except OSError:
        return True
    finally:
        try:
            s.close()
        except OSError:
            pass


def find_sim() -> Optional[Path]:
    env = os.environ.get("GRBLHAL_SIM")
    if env and Path(env).is_file():
        return Path(env)
    for name in ("grblHAL_sim.exe", "grblHAL_sim"):
        p = VENDOR_BIN / name
        if p.is_file():
            return p
    return None


def preflight() -> LayerResult:
    t0 = time.time()
    arts: List[str] = []
    sim = find_sim()
    if not sim:
        return LayerResult(
            id="L0",
            name="preflight",
            status="fail",
            exit_code=2,
            detail="grblHAL_sim not found under vendor/grblhal_sim/bin or GRBLHAL_SIM",
            duration_s=time.time() - t0,
        )
    arts.append(str(sim))
    # Windows runtime DLLs next to exe (MinGW builds)
    missing_dll: List[str] = []
    if sys.platform.startswith("win"):
        for dll in ("libgcc_s_seh-1.dll", "libstdc++-6.dll", "libwinpthread-1.dll"):
            p = sim.parent / dll
            if not p.is_file():
                missing_dll.append(dll)
    # probe -h does not exit on some builds; use -v with short timeout
    try:
        proc = subprocess.run(
            [str(sim), "-v"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(sim.parent),
        )
        ver = ((proc.stdout or "") + (proc.stderr or "")).strip()[:200]
    except subprocess.TimeoutExpired:
        ver = "timeout on -v (ok if binary still present)"
    except OSError as exc:
        return LayerResult(
            id="L0",
            name="preflight",
            status="fail",
            exit_code=2,
            detail=f"cannot execute sim: {exc}",
            duration_s=time.time() - t0,
            artifacts=arts,
        )

    busy = [p for p in (7681, 7682) if not _port_free(p)]
    detail_parts = [f"sim={sim.name}", f"version_snip={ver!r}"]
    if missing_dll:
        detail_parts.append(f"missing_dll={missing_dll}")
    if busy:
        detail_parts.append(f"ports_busy={busy} (runners may fail to bind)")

    # missing DLL is hard fail on Windows; busy ports soft-fail into detail only
    status = "fail" if missing_dll else "pass"
    return LayerResult(
        id="L0",
        name="preflight",
        status=status,
        exit_code=0 if status == "pass" else 2,
        detail="; ".join(detail_parts),
        duration_s=round(time.time() - t0, 2),
        artifacts=arts,
    )


def run_cmd(cmd: List[str], cwd: Path) -> tuple[int, float, str]:
    t0 = time.time()
    print("RUN:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), env=os.environ.copy())
    return proc.returncode, round(time.time() - t0, 2), ""


def honesty_layer() -> LayerResult:
    t0 = time.time()
    stubs = FZ_ROOT / "hardware_sim" / "product_stubs.md"
    text = stubs.read_text(encoding="utf-8") if stubs.is_file() else ""
    gaps = [
        "paper_path_unsimulated",
        "bt_state_unsimulated",
        "i2s_panel_unsimulated",
        "true_soft_limit_trip_weak",
        "not_product_firmware_binary",
        "not_chip_qemu",
    ]
    return LayerResult(
        id="L4",
        name="honesty_product_gaps",
        status="pass",
        exit_code=0,
        detail=(
            "Recorded unsimulated product gaps (must not claim G3b/BT from this green). "
            f"stub_bytes={len(text)}; gaps={gaps}"
        ),
        duration_s=round(time.time() - t0, 2),
        artifacts=[str(stubs)] if stubs.is_file() else [],
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Windows full host SIL (grblHAL_sim stack)")
    ap.add_argument("--skip-protocol", action="store_true")
    ap.add_argument("--skip-hardware", action="store_true")
    ap.add_argument("--skip-unit", action="store_true")
    ap.add_argument(
        "--hw-fast",
        action="store_true",
        help="hardware_sim --fast (-t 0; plant hold may skip)",
    )
    ap.add_argument(
        "--with-validator",
        action="store_true",
        help="pass through to protocol_sim --with-validator",
    )
    ap.add_argument(
        "--with-chip-probe",
        action="store_true",
        help="run chip_sim/probe_chip_tools.py (optional L5; soft by default)",
    )
    ap.add_argument(
        "--require-chip-tool",
        action="store_true",
        help="with --with-chip-probe, fail if no qemu/wokwi/renode on PATH",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON report path (default results/win_full_sim_report.json)",
    )
    args = ap.parse_args(argv)

    RESULTS.mkdir(parents=True, exist_ok=True)
    layers: List[LayerResult] = []

    # Ensure sim env for children
    sim = find_sim()
    if sim:
        os.environ.setdefault("GRBLHAL_SIM", str(sim))
        val = sim.parent / "grblHAL_validator.exe"
        if val.is_file():
            os.environ.setdefault("GRBLHAL_VALIDATOR", str(val))

    pf = preflight()
    layers.append(pf)
    if pf.status != "pass":
        return _finish(layers, args.out, overall=2)

    if not args.skip_protocol:
        cmd = [
            sys.executable,
            str(FZ_ROOT / "protocol_sim" / "run_regression.py"),
            "--start-sim",
        ]
        if args.with_validator:
            cmd.append("--with-validator")
        code, dur, _ = run_cmd(cmd, FZ_ROOT)
        layers.append(
            LayerResult(
                id="L1",
                name="protocol_sim",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=dur,
                detail="ok/error/ALARM cases vs grblHAL_sim",
                artifacts=[
                    str(FZ_ROOT / "protocol_sim" / "results" / "last_report.json")
                ],
            )
        )
    else:
        layers.append(
            LayerResult(id="L1", name="protocol_sim", status="skip", detail="--skip-protocol")
        )

    if not args.skip_hardware:
        cmd = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_hw_sim.py"),
            "--start-sim",
        ]
        if args.hw_fast:
            cmd.append("--fast")
        code, dur, _ = run_cmd(cmd, FZ_ROOT)
        layers.append(
            LayerResult(
                id="L2",
                name="hardware_sim",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=dur,
                detail="MPos + step/block + plant feed-hold (not product paper)",
                artifacts=[
                    str(FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json"),
                    str(FZ_ROOT / "hardware_sim" / "results" / "step_last.log"),
                ],
            )
        )
    else:
        layers.append(
            LayerResult(id="L2", name="hardware_sim", status="skip", detail="--skip-hardware")
        )

    if not args.skip_unit:
        t0 = time.time()
        code1 = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "hardware_sim",
                "-p",
                "test_*.py",
                "-q",
            ],
            cwd=str(FZ_ROOT),
        ).returncode
        code2 = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "hil",
                "-p",
                "test_*.py",
                "-q",
            ],
            cwd=str(FZ_ROOT),
        ).returncode
        code3 = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "chip_sim",
                "-p",
                "test_*.py",
                "-q",
            ],
            cwd=str(FZ_ROOT),
        ).returncode
        code = 0 if code1 == 0 and code2 == 0 and code3 == 0 else 1
        layers.append(
            LayerResult(
                id="L3",
                name="unit_offline",
                status="pass" if code == 0 else "fail",
                exit_code=code,
                duration_s=round(time.time() - t0, 2),
                detail="hardware_sim + hil + chip_sim unit tests (no serial board)",
            )
        )
    else:
        layers.append(
            LayerResult(id="L3", name="unit_offline", status="skip", detail="--skip-unit")
        )

    layers.append(honesty_layer())

    if args.with_chip_probe:
        t0 = time.time()
        chip_cmd = [
            sys.executable,
            str(FZ_ROOT / "chip_sim" / "probe_chip_tools.py"),
            "--firmware-hint",
        ]
        if args.require_chip_tool:
            chip_cmd.append("--require-any")
        code, dur, _ = run_cmd(chip_cmd, FZ_ROOT)
        # Soft by default (probe exits 0 without tools); hard only with --require-chip-tool
        st = "pass" if code == 0 else "fail"
        layers.append(
            LayerResult(
                id="L5",
                name="chip_sim_probe",
                status=st,
                exit_code=code,
                duration_s=dur if dur else round(time.time() - t0, 2),
                detail=(
                    "inventory Espressif QEMU / Wokwi / Renode; "
                    "not product gate; see fusion catalog"
                ),
                artifacts=[str(FZ_ROOT / "results" / "chip_probe.json")],
            )
        )
    else:
        layers.append(
            LayerResult(
                id="L5",
                name="chip_sim_probe",
                status="skip",
                detail="omit --with-chip-probe; host SIL does not need chip tools",
            )
        )

    hard_fail = any(x.status == "fail" for x in layers)
    return _finish(layers, args.out, overall=1 if hard_fail else 0)


def _finish(
    layers: List[LayerResult], out: Optional[Path], overall: int
) -> int:
    report: Dict[str, Any] = {
        "suite": "win_full_sim",
        "fidelity": "host_sil_grblhal_not_product_esp32",
        "platform": sys.platform,
        "overall_exit": overall,
        "overall_status": "pass" if overall == 0 else "fail",
        "claims_forbidden": [
            "product_paper_bt_verified",
            "chip_qemu_full_stack",
            "wifi_ota_verified",
            "this_fork_gcode_equals_grblhal",
        ],
        "layers": [asdict(x) for x in layers],
        "how_to_board": "python scripts/hil_to_gate.py --port COMx",
        "references": [
            "https://github.com/grblHAL/Simulator",
            "https://svn.io-engineering.com:8443/?driver=Simulator",
            "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html",
            "https://docs.wokwi.com/wokwi-ci/getting-started",
            "https://renode.io/",
            "docs/specs/2026-07-14-opensource-sim-fusion-catalog.md",
            "docs/specs/2026-07-14-hardware-sim-optimization-design.md",
            "docs/specs/2026-07-14-software-fullchain-sim-design.md",
        ],
        "fusion_catalog": "docs/specs/2026-07-14-opensource-sim-fusion-catalog.md",
    }
    path = out or (RESULTS / "win_full_sim_report.json")
    if not path.is_absolute():
        path = FZ_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== win_full_sim ===")
    for x in layers:
        print(
            f"  [{x.status.upper():4}] {x.id} {x.name}"
            + (f" exit={x.exit_code}" if x.exit_code is not None else "")
            + (f" ({x.duration_s}s)" if x.duration_s else "")
            + (f" — {x.detail[:120]}" if x.detail else "")
        )
    print(f"overall: {report['overall_status']} exit={overall}")
    print(f"report: {path}")
    return overall


if __name__ == "__main__":
    raise SystemExit(main())
