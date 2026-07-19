#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a 2/4/8/16 MB SPI flash image for Espressif QEMU from PlatformIO artifacts.

Official pattern (ESP-IDF / esptool merge_bin):
  bootloader @ 0x1000, partition table @ 0x8000, app @ 0x10000
  flash size must be 2/4/8/16 MB for qemu-system-xtensa -machine esp32

Refs:
  https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32/README.md
  https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html

Does NOT prove product paper/BT; experimental chip SIL helper only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results" / "qemu"

# Classic ESP32 Arduino / IDF defaults
DEFAULT_OFFSETS = {
    "bootloader": 0x1000,
    "partitions": 0x8000,
    "app": 0x10000,
}

SIZE_MAP = {
    "2MB": 2 * 1024 * 1024,
    "4MB": 4 * 1024 * 1024,
    "8MB": 8 * 1024 * 1024,
    "16MB": 16 * 1024 * 1024,
}


def find_bootloader(
    pio_packages: Optional[Path] = None,
    *,
    flash_mode: str = "dio",
) -> Optional[Path]:
    """
    Pick Arduino-ESP32 SDK bootloader.

    Default **dio** for QEMU: guest log often shows mode:DIO; community PIO+QEMU
    (xtensa-qemetsu) uses --flash_mode dio in merge_bin.
    Use flash_mode=qio to match Grbl platformio.ini board_build.flash_mode=qio.
    """
    roots: List[Path] = []
    if pio_packages:
        roots.append(pio_packages)
    home = Path(os.environ.get("USERPROFILE", os.environ.get("HOME", "")))
    roots.append(home / ".platformio" / "packages")
    mode = (flash_mode or "dio").lower()
    if mode == "qio":
        names = (
            "bootloader_qio_80m.bin",
            "bootloader_qio_40m.bin",
            "bootloader_dio_80m.bin",
            "bootloader_dio_40m.bin",
        )
    else:
        names = (
            "bootloader_dio_80m.bin",
            "bootloader_dio_40m.bin",
            "bootloader_qio_80m.bin",
            "bootloader_qio_40m.bin",
        )
    for root in roots:
        if not root.is_dir():
            continue
        for pkg in sorted(root.glob("framework-arduinoespressif32*")):
            sdk_bin = pkg / "tools" / "sdk" / "bin"
            for name in names:
                p = sdk_bin / name
                if p.is_file():
                    return p
    return None


def find_build_artifacts(grbl_root: Path, pio_env: str = "release") -> Dict[str, Optional[Path]]:
    build = grbl_root / ".pio" / "build" / pio_env
    if not build.is_dir():
        # any env
        builds = list((grbl_root / ".pio" / "build").glob("*/firmware.bin"))
        if builds:
            build = builds[0].parent
    return {
        "firmware": (build / "firmware.bin") if (build / "firmware.bin").is_file() else None,
        "partitions": (build / "partitions.bin")
        if (build / "partitions.bin").is_file()
        else None,
        "build_dir": build if build.is_dir() else None,
    }


def pure_merge(
    parts: List[Tuple[int, Path]],
    out: Path,
    fill_size: int,
    fill_byte: int = 0xFF,
) -> None:
    """Write sparse segments into a filled flash image (esptool-compatible layout)."""
    img = bytearray([fill_byte]) * fill_size
    for offset, path in parts:
        data = path.read_bytes()
        end = offset + len(data)
        if end > fill_size:
            raise ValueError(
                f"{path.name} at 0x{offset:x} length {len(data)} exceeds flash size {fill_size}"
            )
        img[offset:end] = data
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(img))


def try_esptool_merge(
    parts: List[Tuple[int, Path]],
    out: Path,
    fill_label: str,
    esptool: Optional[str],
) -> bool:
    if not esptool:
        return False
    import subprocess

    cmd = [
        esptool,
        "--chip",
        "esp32",
        "merge_bin",
        "--fill-flash-size",
        fill_label,
        "-o",
        str(out),
    ]
    for off, path in parts:
        cmd.extend([f"0x{off:x}", str(path)])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return proc.returncode == 0 and out.is_file()
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_esptool() -> Optional[str]:
    for name in ("esptool", "esptool.py", "esptool.exe"):
        w = shutil.which(name)
        if w:
            return w
    # common user Scripts
    home = Path(os.environ.get("USERPROFILE", ""))
    cand = home / "AppData" / "Roaming" / "Python" / "Python314" / "Scripts" / "esptool.exe"
    if cand.is_file():
        return str(cand)
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build QEMU flash image from PIO bins")
    ap.add_argument(
        "--grbl-root",
        type=Path,
        default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")),
    )
    ap.add_argument("--bootloader", type=Path, default=None)
    ap.add_argument("--partitions", type=Path, default=None)
    ap.add_argument("--firmware", type=Path, default=None)
    ap.add_argument(
        "--flash-size",
        default="4MB",
        choices=list(SIZE_MAP.keys()),
        help="QEMU only accepts 2/4/8/16 MB",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="default results/qemu/flash_image_4mb.bin",
    )
    ap.add_argument("--prefer-esptool", action="store_true")
    ap.add_argument(
        "--flash-mode",
        default="dio",
        choices=("dio", "qio"),
        help="bootloader variant preference (default dio for QEMU)",
    )
    ap.add_argument(
        "--pio-env",
        default="release",
        help="PlatformIO env dir under .pio/build to take firmware from (e.g. qemu)",
    )
    args = ap.parse_args(argv)

    grbl = args.grbl_root
    arts = find_build_artifacts(grbl, pio_env=args.pio_env) if grbl.is_dir() else {}
    boot = args.bootloader or find_bootloader(flash_mode=args.flash_mode)
    part = args.partitions or arts.get("partitions")
    firm = args.firmware or arts.get("firmware")

    missing = [n for n, p in (("bootloader", boot), ("partitions", part), ("firmware", firm)) if not p]
    if missing:
        print(
            "ERROR: missing " + ", ".join(missing) + "\n"
            "  Build firmware: cd GRBL_ROOT && pio run -e release\n"
            "  Bootloader: PlatformIO framework-arduinoespressif32 tools/sdk/bin/\n"
            "  Or pass --bootloader/--partitions/--firmware",
            file=sys.stderr,
        )
        return 2

    assert boot and part and firm
    fill = SIZE_MAP[args.flash_size]
    out = args.out or (RESULTS / f"flash_image_{args.flash_size.lower()}.bin")
    if not out.is_absolute():
        out = FZ_ROOT / out

    parts = [
        (DEFAULT_OFFSETS["bootloader"], Path(boot)),
        (DEFAULT_OFFSETS["partitions"], Path(part)),
        (DEFAULT_OFFSETS["app"], Path(firm)),
    ]

    method = "pure_python"
    esptool = find_esptool()
    if args.prefer_esptool and esptool:
        if try_esptool_merge(parts, out, args.flash_size, esptool):
            method = f"esptool:{esptool}"
        else:
            pure_merge(parts, out, fill)
            method = "pure_python_fallback"
    else:
        pure_merge(parts, out, fill)

    meta = {
        "out": str(out),
        "size": out.stat().st_size,
        "flash_size_label": args.flash_size,
        "method": method,
        "segments": [
            {
                "name": n,
                "offset": f"0x{o:x}",
                "path": str(p),
                "bytes": p.stat().st_size,
                "mtime": p.stat().st_mtime,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for n, (o, p) in zip(("bootloader", "partitions", "app"), parts)
        ],
        "qemu_note": "experimental; Arduino product may panic/hang under QEMU",
        "run_hint": (
            f'qemu-system-xtensa -nographic -machine esp32 '
            f'-drive file={out},if=mtd,format=raw '
            f'-global driver=timer.esp32.timg,property=wdt_disable,value=true'
        ),
    }
    meta_path = out.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print(f"wrote {out} ({out.stat().st_size} bytes) via {method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
