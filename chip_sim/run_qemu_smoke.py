#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optional Espressif QEMU smoke: run flash image, capture serial for a few seconds.

Interactive UART smoke: sends \\r\\n, $I, $$ and checks for Grbl protocol responses.
Startup log oracle: classifies boot/fatal patterns.

Official package must be started so ROM is found under share/qemu/ (run from
package root = parent of bin/). Do not pass raw rom.bin as -bios (not ELF).

Exit codes:
  0  ROM/bootloader path produced boot markers (even if app panics)
  1  startup oracle fails without panic exemption (silent restart loop /
     ready timeout / no boot markers), or QEMU ran with a host error
  2  missing qemu or flash image
  3  QEMU process error

Not a product gate. Host SIL remains win_full_sim / protocol_sim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from startup_log_oracle import analyze_startup_log


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results" / "qemu"
VENDOR_QEMU = FZ_ROOT / "vendor" / "espressif_qemu"
PANIC_BASELINE = Path(__file__).resolve().parent / "qemu_panic_baseline.json"

# [MSG:Using machine:Custom 3-Axis HR4988]
MACHINE_BANNER_RE = re.compile(r"\[MSG:Using machine:([^\]]+)\]")
# assertion "..." failed: file ".../bt/bt.c", line 1134, function: esp_bt_controller_init
ASSERT_PANIC_RE = re.compile(r'assertion "[^"]*" failed: file "([^"]+)", line (\d+)')
GURU_PANIC_RE = re.compile(r"Guru Meditation Error: Core\s+\d+ panic'ed \(([^)]+)\)")


def expected_machine_name(grbl_root: Path) -> Optional[str]:
    """Resolve MACHINE_NAME from GRBL_ROOT's current Machine.h selection.

    Identity guard: QEMU boots whatever firmware.bin sits in .pio/build — a
    stale or MACHINE_FILENAME-overridden build silently tests the wrong
    machine config (seen 2026-07-20: tree=custom_3axis_hr4988, image=SPI_DAISY_4X).
    """
    src = grbl_root / "Grbl_Esp32" / "src"
    try:
        text = (src / "Machine.h").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'^\s*#\s*include\s+"(Machines/[^"]+)"', text, re.M)
    if not m:
        return None
    try:
        htext = (src / m.group(1)).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    names = re.findall(r'#define\s+MACHINE_NAME\s+"([^"]+)"', htext)
    return names[0] if names else None


def panic_fingerprints(text: str) -> List[str]:
    """Stable panic identities for baseline comparison (path tail + line / cause)."""
    fps = set()
    for m in ASSERT_PANIC_RE.finditer(text):
        tail = "/".join(m.group(1).replace("\\", "/").split("/")[-2:])
        fps.add(f"assert:{tail}:{m.group(2)}")
    for m in GURU_PANIC_RE.finditer(text):
        fps.add(f"guru:{m.group(1).strip()}")
    return sorted(fps)


def load_panic_baseline() -> List[str]:
    try:
        data = json.loads(PANIC_BASELINE.read_text(encoding="utf-8"))
        return [str(x) for x in data.get("allowed", [])]
    except (OSError, ValueError):
        return []


def newest_source_mtime(grbl_root: Path) -> Optional[float]:
    """Newest firmware source mtime — detects builds older than the code."""
    newest: Optional[float] = None
    try:
        for p in (grbl_root / "Grbl_Esp32" / "src").rglob("*"):
            if p.suffix.lower() in (".h", ".hpp", ".c", ".cpp", ".ino"):
                m = p.stat().st_mtime
                if newest is None or m > newest:
                    newest = m
    except OSError:
        return None
    return newest


def _sha256(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def find_qemu() -> Optional[Path]:
    env = os.environ.get("ESP_QEMU") or os.environ.get("QEMU_SYSTEM_XTENSA")
    if env and Path(env).is_file():
        return Path(env)
    w = shutil.which("qemu-system-xtensa")
    if w:
        return Path(w)
    for p in (
        VENDOR_QEMU / "extract" / "qemu" / "bin" / "qemu-system-xtensa.exe",
        VENDOR_QEMU / "qemu" / "bin" / "qemu-system-xtensa.exe",
        VENDOR_QEMU / "bin" / "qemu-system-xtensa.exe",
    ):
        if p.is_file():
            return p
    if VENDOR_QEMU.is_dir():
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
    parent = qemu.parent
    if (parent.parent / "share" / "qemu").is_dir():
        return parent.parent
    if (parent / "share" / "qemu").is_dir():
        return parent
    if (VENDOR_QEMU / "share" / "qemu").is_dir() and qemu.is_relative_to(VENDOR_QEMU):
        return VENDOR_QEMU
    if (VENDOR_QEMU / "extract" / "qemu" / "share" / "qemu").is_dir():
        return VENDOR_QEMU / "extract" / "qemu"
    return parent


def _reader_pump(stream: Any, sink: queue.Queue[Optional[str]]) -> None:
    """Copy *stream* lines into *sink* forever; put None on EOF (daemon thread)."""
    try:
        for line in iter(stream.readline, ""):
            sink.put(line)
    except (OSError, ValueError):
        pass
    finally:
        sink.put(None)


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
    ap.add_argument(
        "--interactive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="send \\r\\n, $I, $$ to probe Grbl protocol (default True)",
    )
    ap.add_argument(
        "--ready-marker",
        action="append",
        default=[],
        dest="ready_markers",
        help="ready marker for startup oracle (repeatable, default Grbl)",
    )
    ap.add_argument(
        "--grbl-root",
        type=Path,
        default=Path(os.environ.get("GRBL_ROOT", "")) if os.environ.get("GRBL_ROOT") else None,
        help="firmware tree for machine identity check (default env GRBL_ROOT)",
    )
    ap.add_argument(
        "--skip-identity",
        action="store_true",
        help="skip firmware machine identity check",
    )
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
            stdin=subprocess.PIPE,
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
    interactive_sent: List[str] = []
    out_queue: queue.Queue[Optional[str]] = queue.Queue()
    assert proc.stdout is not None
    reader = threading.Thread(target=_reader_pump, args=(proc.stdout, out_queue), daemon=True)
    reader.start()
    pending_sends = ["\r\n", "$I\n", "$$\n"] if args.interactive else []
    next_send_at = time.time() + 2.0
    # Grbl ready prompt: "Grbl 1.3a ['$' for help]" — probes sent before this
    # line are consumed by a panicking earlier boot and never answered.
    ready_line_re = re.compile(r"Grbl\s+\S+\s+\['\$'", re.I)
    probes_rearmed = 0

    try:
        while True:
            if time.time() >= deadline:
                break
            if pending_sends and time.time() >= next_send_at and proc.poll() is None:
                data = pending_sends.pop(0)
                interactive_sent.append(data.strip())
                try:
                    if proc.stdin is not None:
                        proc.stdin.write(data)
                        proc.stdin.flush()
                except (OSError, ValueError):
                    pass
                next_send_at = time.time() + 1.0
                continue
            try:
                item = out_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                break  # output stream ended; no more output is possible
            chunks.append(item)
            sys.stdout.write(item)
            sys.stdout.flush()
            if args.interactive and ready_line_re.search(item) and probes_rearmed < 2:
                # Fresh ready prompt (possibly after a panic-reboot): re-arm the
                # full probe sequence so the responsive boot actually gets asked.
                probes_rearmed += 1
                pending_sends = ["\r\n", "$I\n", "$$\n"]
                next_send_at = time.time() + 0.3
                # Give the answering boot time to reply even near the deadline.
                deadline = max(deadline, time.time() + 6.0)
            elif pending_sends and re.search(r"Grbl|\[MSG:", item, re.I):
                # Grbl banner sighting: probe immediately instead of waiting
                # for the fixed 2s schedule (matters on panic-looping images).
                next_send_at = min(next_send_at, time.time())
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        if proc.stdin:
            try:
                proc.stdin.close()
            except OSError:
                pass

    text = "".join(chunks)
    log_path.write_text(text, encoding="utf-8")

    # Pattern scoring
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
    qemu_host_error = bool(
        re.search(
            r"could not load ELF|ROM code binary not found|Error: -bios argument",
            text,
        )
    )

    # Protocol smoke: count Grbl protocol responses. "ok" is matched loosely
    # (\bok\b); only used as responded=any(>0), not as an exact reply count.
    protocol_hits = {
        "[VER:": len(re.findall(r"\[VER:", text)),
        "[PARAM": len(re.findall(r"\[PARAM", text)),
        "ok": len(re.findall(r"\bok\b", text)),
    }
    protocol_responded = any(v > 0 for v in protocol_hits.values())

    # Startup oracle
    ready_markers = args.ready_markers or ["Grbl"]
    oracle_verdict = analyze_startup_log(text, ready_markers=ready_markers, max_boots=2)

    # Firmware machine identity: banner vs current source tree selection
    banner_m = MACHINE_BANNER_RE.search(text)
    banner_machine = banner_m.group(1).strip() if banner_m else None
    expected_machine = (
        expected_machine_name(args.grbl_root)
        if (args.grbl_root and not args.skip_identity)
        else None
    )
    machine_mismatch = False
    if banner_machine and expected_machine:
        b, e = banner_machine.lower(), expected_machine.lower()
        machine_mismatch = e not in b and b not in e

    # Panic fingerprint baseline: known-in-QEMU panics are exempt, new ones red
    fps = panic_fingerprints(text)
    allowed_fps = load_panic_baseline()
    new_fps = [f for f in fps if f not in allowed_fps]

    # ---------- exit code (honesty first) ----------
    exit_code: int = 0
    if qemu_host_error and not rom_boot_ok:
        print("FAIL: QEMU host error without guest boot")
        exit_code = 1
    elif not text.strip():
        if args.allow_empty:
            print("WARN: empty UART but --allow-empty")
        else:
            print("FAIL: no UART output")
            exit_code = 1
    elif args.require_app and not app_ok:
        print("FAIL: --require-app but no Grbl/app banner")
        exit_code = 1
    elif args.expect and not extra_hits:
        print("FAIL: expected patterns not found:", args.expect)
        exit_code = 1
    elif not rom_boot_ok:
        print("FAIL: no ROM/bootloader markers (check cwd/share ROM + flash image)")
        exit_code = 1
    elif machine_mismatch:
        print(
            f"FAIL: firmware machine identity mismatch — banner={banner_machine!r} "
            f"but source tree selects {expected_machine!r}. Stale or "
            "MACHINE_FILENAME-overridden firmware.bin; rebuild: pio run -e release"
        )
        exit_code = 1
    elif oracle_verdict["status"] == "fail":
        fatal_kinds = {e["kind"] for e in oracle_verdict.get("fatal_events", [])}
        panic_kinds = {"guru_meditation", "panic"}
        # Exemption applies only when every fatal is panic-family (or the
        # restart/ready markers a panic-loop produces): brownout, watchdog,
        # radio/filesystem/task failures are real anomalies and must fail.
        exemptable = panic_kinds | {"restart_loop", "ready_timeout"}
        has_panic = bool(fatal_kinds & panic_kinds)
        if new_fps:
            print(
                f"FAIL: new panic fingerprint(s) not in baseline: {new_fps} "
                f"(baseline: {PANIC_BASELINE.name})"
            )
            exit_code = 1
        elif has_panic and fatal_kinds <= exemptable:
            print(
                "PASS (experimental): ROM boot ok, startup oracle reports "
                "fail with baseline-known panic exemption"
            )
            exit_code = 0
        else:
            print(f"FAIL: startup oracle fatal events: {sorted(fatal_kinds)}")
            exit_code = 1
    else:
        # Oracle pass
        if new_fps:
            print(f"FAIL: new panic fingerprint(s) not in baseline: {new_fps}")
            exit_code = 1
        elif protocol_responded:
            print("PASS: boot + protocol response:", protocol_hits)
        else:
            print("PASS (experimental): boot ok, no protocol response")
        exit_code = 0 if not new_fps else 1

    # ---------- report ----------
    flash_sidecar: Dict[str, Any] = {}
    try:
        flash_sidecar = json.loads(flash.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    # Build staleness: identity check catches wrong-machine images, this
    # catches right-machine-but-older-than-source images (evidence about
    # code that has since changed). Warning only — rebuilds may lag on purpose.
    firmware_stale: Optional[bool] = None
    if args.grbl_root:
        app_seg = next(
            (s for s in (flash_sidecar.get("segments") or []) if s.get("name") == "app"),
            None,
        )
        fw_mtime = (app_seg or {}).get("mtime")
        src_mtime = newest_source_mtime(args.grbl_root)
        if isinstance(fw_mtime, (int, float)) and src_mtime is not None:
            firmware_stale = fw_mtime < src_mtime
            if firmware_stale:
                print(
                    "WARN: firmware image is older than the newest source file "
                    "under GRBL_ROOT src/ — evidence may describe stale code. "
                    "Rebuild: pio run -e qemu (or release) then build_flash_image.py"
                )
    report = {
        "suite": "qemu_smoke",
        "fidelity": "experimental_chip_sil_not_product_gate",
        "qemu": str(qemu),
        "package_root": str(pkg),
        "flash": str(flash),
        "flash_sha256": _sha256(flash),
        "flash_segments": flash_sidecar.get("segments"),
        "firmware_stale_vs_source": firmware_stale,
        "machine_identity": {
            "banner": banner_machine,
            "expected_from_source": expected_machine,
            "match": (not machine_mismatch) if (banner_machine and expected_machine) else None,
        },
        "panic_fingerprints": fps,
        "panic_baseline_allowed": allowed_fps,
        "new_panic_fingerprints": new_fps,
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
        "interactive_sent": interactive_sent,
        "protocol_smoke": {
            "sent": interactive_sent,
            "hits": protocol_hits,
            "responded": protocol_responded,
        },
        "startup_oracle": oracle_verdict,
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

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
