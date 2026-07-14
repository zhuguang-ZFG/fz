#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional Espressif QEMU smoke: run flash image, capture serial for a few seconds.

Official package must be started so ROM is found under share/qemu/ (run from
package root = parent of bin/). Do not pass raw rom.bin as -bios (not ELF).

Exit codes:
  0  ROM/bootloader path produced boot markers (even if app panics)
  1  QEMU ran but no boot markers
  2  missing qemu or flash image
  3  QEMU process error

Not a product gate. Host SIL remains win_full_sim / protocol_sim.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results" / "qemu"
VENDOR_QEMU = FZ_ROOT / "vendor" / "espressif_qemu"


def find_qemu() -> Optional[Path]:
    env = os.environ.get("ESP_QEMU") or os.environ.get("QEMU_SYSTEM_XTENSA")
    if env and Path(env).is_file():
        return Path(env)
    w = shutil.which("qemu-system-xtensa")
    if w:
        return Path(w)
    # Prefer full package tree (share/qemu ROM) over bare bin/ copy
    for p in (
        VENDOR_QEMU / "extract" / "qemu" / "bin" / "qemu-system-xtensa.exe",
        VENDOR_QEMU / "qemu" / "bin" / "qemu-system-xtensa.exe",
        VENDOR_QEMU / "bin" / "qemu-system-xtensa.exe",
    ):
        if p.is_file():
            return p
    if VENDOR_QEMU.is_dir():
        # Prefer any path that has sibling ../share/qemu
        found: List[Path] = list(VENDOR_QEMU.rglob("qemu-system-xtensa.exe"))
        found += list(VENDOR_QEMU.rglob("qemu-system-xtensa"))
        for p in found:
            if (p.parent.parent / "share" / "qemu").is_dir():
                return p
        if found:
            return found[0]
    return None


def package_root_for(qemu: Path) -> Path:
    """Directory that contains bin/ and share/qemu/ for Espressif builds."""
    # .../qemu/bin/qemu-system-xtensa.exe → .../qemu
    parent = qemu.parent
    if (parent.parent / "share" / "qemu").is_dir():
        return parent.parent
    if (parent / "share" / "qemu").is_dir():
        return parent
    # vendored: vendor/espressif_qemu/{bin,share}
    if (VENDOR_QEMU / "share" / "qemu").is_dir() and qemu.is_relative_to(VENDOR_QEMU):
        return VENDOR_QEMU
    if (VENDOR_QEMU / "extract" / "qemu" / "share" / "qemu").is_dir():
        return VENDOR_QEMU / "extract" / "qemu"
    return parent


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="QEMU serial smoke (experimental)")
    ap.add_argument(
        "--flash",
        type=Path,
        default=None,
        help="flash image (default results/qemu/flash_image_4mb.bin)",
    )
    ap.add_argument("--timeout", type=float, default=15.0, help="seconds to capture UART")
    ap.add_argument(
        "--expect",
        action="append",
        default=[],
        help="extra regex that must appear (repeatable)",
    )
    ap.add_argument(
        "--require-app",
        action="store_true",
        help="fail unless Grbl/app banner seen (strict; product often panics)",
    )
    ap.add_argument(
        "--allow-empty",
        action="store_true",
        help="exit 0 even if no UART",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    qemu = find_qemu()
    if not qemu:
        print(
            "ERROR: qemu-system-xtensa not found.\n"
            "  Install: chip_sim/install_qemu_windows.ps1\n"
            "  Or set ESP_QEMU=path\\to\\qemu-system-xtensa.exe\n"
            "  Release: https://github.com/espressif/qemu/releases",
            file=sys.stderr,
        )
        return 2

    flash = args.flash or (RESULTS / "flash_image_4mb.bin")
    if not flash.is_absolute():
        flash = FZ_ROOT / flash
    if not flash.is_file():
        print(
            f"ERROR: flash image missing: {flash}\n"
            "  Run: python chip_sim/build_flash_image.py --grbl-root <GRBL_ROOT>",
            file=sys.stderr,
        )
        return 2

    RESULTS.mkdir(parents=True, exist_ok=True)
    log_path = args.out or (RESULTS / "qemu_smoke_uart.log")
    if not log_path.is_absolute():
        log_path = FZ_ROOT / log_path

    pkg = package_root_for(qemu)
    # Prefer exe under pkg/bin when present (same package as share/)
    pkg_exe = pkg / "bin" / qemu.name
    if pkg_exe.is_file():
        qemu = pkg_exe

    cmd = [
        str(qemu),
        "-nographic",
        "-machine",
        "esp32",
        "-drive",
        f"file={flash},if=mtd,format=raw",
        "-global",
        "driver=timer.esp32.timg,property=wdt_disable,value=true",
    ]
    print("RUN:", " ".join(cmd))
    print(f"cwd={pkg} timeout={args.timeout}s log={log_path}")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(pkg),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        print(f"ERROR: failed to start QEMU: {exc}", file=sys.stderr)
        return 3

    chunks: List[str] = []
    deadline = time.time() + args.timeout
    try:
        assert proc.stdout is not None
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line:
                chunks.append(line)
                sys.stdout.write(line)
                sys.stdout.flush()
            elif proc.poll() is not None:
                rest = proc.stdout.read() or ""
                if rest:
                    chunks.append(rest)
                    sys.stdout.write(rest)
                break
            else:
                time.sleep(0.05)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    text = "".join(chunks)
    log_path.write_text(text, encoding="utf-8")

    # Ignore QEMU host stderr-style lines for pattern scoring
    boot_markers = [
        r"rst:0x",
        r"boot:0x",
        r"SPI_FAST_FLASH_BOOT",
        r"entry 0x",
        r"load:0x40078",
        r"ets Jul",
    ]
    panic_markers = [
        r"Guru Meditation",
        r"panic'ed",
        r"Rebooting\.\.\.",
    ]
    app_markers = [
        r"\bGrbl\b",
        r"Grbl_Esp32",
        r"\[MSG:",
        r"cpu_start",
    ]

    boot_hits = [p for p in boot_markers if re.search(p, text, re.I)]
    panic_hits = [p for p in panic_markers if re.search(p, text, re.I)]
    app_hits = [p for p in app_markers if re.search(p, text, re.I)]
    extra_hits = [p for p in (args.expect or []) if re.search(p, text, re.I)]

    rom_boot_ok = bool(boot_hits)
    app_ok = bool(app_hits)
    # Host-side QEMU failures (not guest "Guru Meditation Error")
    qemu_host_error = bool(
        re.search(
            r"could not load ELF|ROM code binary not found|Error: -bios argument",
            text,
        )
    )

    report = {
        "suite": "qemu_smoke",
        "fidelity": "experimental_chip_sil_not_product_gate",
        "qemu": str(qemu),
        "package_root": str(pkg),
        "flash": str(flash),
        "timeout_s": args.timeout,
        "uart_bytes": len(text.encode("utf-8", errors="replace")),
        "rom_boot_ok": rom_boot_ok,
        "app_banner_ok": app_ok,
        "app_panic_seen": bool(panic_hits),
        "boot_hits": boot_hits,
        "panic_hits": panic_hits,
        "app_hits": app_hits,
        "extra_hits": extra_hits,
        "qemu_host_error": qemu_host_error,
        "log": str(log_path),
        "interpretation": (
            "ROM+2nd-stage bootloader reached; app may panic under QEMU "
            "(Arduino Grbl not a supported QEMU target). Not G3b/OTA."
            if rom_boot_ok and panic_hits
            else (
                "ROM boot markers seen"
                if rom_boot_ok
                else "no ESP boot markers"
            )
        ),
        "claims_forbidden": [
            "paper_path_verified",
            "bt_verified",
            "wifi_ota_verified",
            "product_release_ok",
            "arduino_app_stable_under_qemu",
        ],
    }
    rep_path = RESULTS / "qemu_smoke_report.json"
    rep_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if qemu_host_error and not rom_boot_ok:
        print("FAIL: QEMU host error without guest boot")
        return 1
    if not text.strip():
        if args.allow_empty:
            print("WARN: empty UART but --allow-empty")
            return 0
        print("FAIL: no UART output")
        return 1
    if args.require_app and not app_ok:
        print("FAIL: --require-app but no Grbl/app banner")
        return 1
    if args.expect and not extra_hits:
        print("FAIL: expected patterns not found:", args.expect)
        return 1
    if not rom_boot_ok:
        print("FAIL: no ROM/bootloader markers (check cwd/share ROM + flash image)")
        return 1

    if panic_hits and not app_ok:
        print(
            "PASS (experimental): chip ROM+bootloader path works; "
            "app panicked under QEMU (expected for this Arduino product image)"
        )
    elif app_ok:
        print("PASS: boot + app banner seen:", app_hits)
    else:
        print("PASS: boot markers:", boot_hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
