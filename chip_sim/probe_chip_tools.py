#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventory open-source / vendor chip-level simulators on this machine.

Community + official:
  - Espressif QEMU (qemu-system-xtensa / riscv32)
  - Wokwi CLI (wokwi-cli + WOKWI_CLI_TOKEN)
  - Renode

Exit:
  0 always unless --require-any / --require-qemu and missing
  2 requirement not met
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _sha16(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def find_firmware(grbl_root: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not grbl_root or not grbl_root.is_dir():
        return None
    candidates = [
        grbl_root / ".pio" / "build" / "release" / "firmware.bin",
        grbl_root / ".pio" / "build" / "release" / "firmware.elf",
    ]
    # first existing bin preferred
    for p in candidates:
        if p.is_file():
            return {
                "path": str(p),
                "size": p.stat().st_size,
                "sha256_16": _sha16(p),
                "note": "Arduino/PIO artifact — not auto-proven under QEMU",
            }
    # glob one bin
    build = grbl_root / ".pio" / "build"
    if build.is_dir():
        bins = list(build.glob("*/firmware.bin"))
        if bins:
            p = bins[0]
            return {
                "path": str(p),
                "size": p.stat().st_size,
                "sha256_16": _sha16(p),
                "note": "Arduino/PIO artifact — not auto-proven under QEMU",
            }
    return None


def probe() -> Dict[str, Any]:
    tools = {
        "qemu_system_xtensa": _which("qemu-system-xtensa"),
        "qemu_system_riscv32": _which("qemu-system-riscv32"),
        "wokwi_cli": _which("wokwi-cli"),
        "renode": _which("renode") or _which("renode.exe"),
        "idf_py": _which("idf.py"),
    }
    # common Windows scoop/user paths (soft hints only)
    extra_hints: List[str] = []
    for base in (
        Path(os.environ.get("USERPROFILE", "")) / ".espressif",
        Path(os.environ.get("IDF_TOOLS_PATH", "")),
        Path("C:/Espressif"),
    ):
        if base and base.is_dir():
            extra_hints.append(str(base))

    has_qemu = bool(tools["qemu_system_xtensa"] or tools["qemu_system_riscv32"])
    has_wokwi = bool(tools["wokwi_cli"])
    has_renode = bool(tools["renode"])
    wokwi_token = bool(os.environ.get("WOKWI_CLI_TOKEN", "").strip())

    report: Dict[str, Any] = {
        "suite": "chip_sim_probe",
        "fidelity": "tool_inventory_not_product_gate",
        "tools": tools,
        "capabilities": {
            "espressif_qemu_on_path": has_qemu,
            "wokwi_cli_on_path": has_wokwi,
            "wokwi_token_set": wokwi_token,
            "renode_on_path": has_renode,
            "any_chip_tool": has_qemu or has_wokwi or has_renode,
        },
        "path_hints": extra_hints,
        "install": {
            "qemu": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html",
            "qemu_releases": "https://github.com/espressif/qemu/releases",
            "wokwi_ci": "https://docs.wokwi.com/wokwi-ci/getting-started",
            "renode": "https://renode.io/",
        },
        "honest_limits": [
            "Arduino Grbl_Esp32 full stack is not guaranteed under Espressif QEMU",
            "QEMU Wi-Fi/BT incomplete vs product radio",
            "Wokwi free tier has monthly simulation minutes",
            "chip green != paper path / BT / true OTA",
        ],
        "firmware": None,
        "references": [
            "docs/specs/2026-07-14-opensource-sim-fusion-catalog.md",
            "https://github.com/grblHAL/Simulator",
        ],
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Probe chip-level simulators")
    ap.add_argument("--require-any", action="store_true", help="exit 2 if no qemu/wokwi/renode")
    ap.add_argument("--require-qemu", action="store_true", help="exit 2 if no qemu-system-*")
    ap.add_argument(
        "--firmware-hint",
        action="store_true",
        help="attach GRBL_ROOT .pio firmware.bin metadata if present",
    )
    ap.add_argument("--grbl-root", type=Path, default=None)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write JSON (default results/chip_probe.json)",
    )
    args = ap.parse_args(argv)

    report = probe()
    if args.firmware_hint:
        grbl = args.grbl_root or Path(os.environ.get("GRBL_ROOT", ""))
        report["firmware"] = find_firmware(grbl if grbl else None)

    out = args.out or (RESULTS / "chip_probe.json")
    if not out.is_absolute():
        out = FZ_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    caps = report["capabilities"]
    print("=== chip_sim probe ===")
    for k, v in report["tools"].items():
        print(f"  {k}: {v or '(not on PATH)'}")
    print(f"  any_chip_tool: {caps['any_chip_tool']}")
    print(f"  wokwi_token_set: {caps['wokwi_token_set']}")
    if report.get("firmware"):
        print(f"  firmware: {report['firmware']}")
    print(f"wrote {out}")
    print("limits:", "; ".join(report["honest_limits"][:2]), "...")

    if args.require_qemu and not caps["espressif_qemu_on_path"]:
        print("ERROR: --require-qemu but qemu-system-* missing", file=sys.stderr)
        return 2
    if args.require_any and not caps["any_chip_tool"]:
        print(
            "ERROR: --require-any but no qemu/wokwi/renode on PATH "
            "(install optional; host SIL does not need them)",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
