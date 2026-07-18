#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for run_qemu_smoke — no real QEMU dependency.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_qemu_smoke import find_qemu, package_root_for
from run_qemu_smoke import main as qemu_main


# ---------- find_qemu / package_root_for ----------

class TestFindQemu(unittest.TestCase):
    """Tests for find_qemu on fake directory trees (no real binary)."""

    def test_find_qemu_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # No qemu binary anywhere
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("run_qemu_smoke.VENDOR_QEMU", td_path / "vendor_qemu"):
                    with mock.patch("run_qemu_smoke.shutil.which", return_value=None):
                        result = find_qemu()
                        self.assertIsNone(result)

    def test_find_qemu_uses_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake_qemu = Path(td) / "qemu-system-xtensa.exe"
            fake_qemu.write_text("fake binary")
            with mock.patch.dict(os.environ, {"ESP_QEMU": str(fake_qemu)}):
                result = find_qemu()
                self.assertEqual(result, fake_qemu)

    def test_package_root_vendored_detect(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # Simulate vendor/espressif_qemu/share/qemu/
            share = td_path / "share" / "qemu"
            share.mkdir(parents=True)
            fake_qemu = td_path / "bin" / "qemu-system-xtensa.exe"
            fake_qemu.parent.mkdir(parents=True)
            fake_qemu.write_text("fake")
            with mock.patch("run_qemu_smoke.VENDOR_QEMU", td_path):
                result = package_root_for(fake_qemu)
                self.assertEqual(result, td_path)


# ---------- protocol_smoke / oracle / exit code matrix ----------

_SAMPLE_BOOT_TEXT = """\
ESP-ROM:esp32
Build:Jun  8 2016
rst:0x1 (POWERON_RESET)
boot:0x13 (SPI_FAST_FLASH_BOOT)
configsip: 0
SPIWP:0xee
mode:DIO, clock div:2
load:0x40078...
entry 0x40078...
Grbl_Esp32 1.1f ['$' for help]
"""

_SAMPLE_PANIC_TEXT = """\
ESP-ROM:esp32
rst:0x1 (POWERON_RESET)
boot:0x13 (SPI_FAST_FLASH_BOOT)
entry 0x40078...
Guru Meditation Error: Core 1 panic'ed
Rebooting...

ets Jul 29 2019 12:21:46
rst:0x3 (SW_RESET)
boot:0x13 (SPI_FAST_FLASH_BOOT)
"""

_SAMPLE_RESPONSE_TEXT = """\
<Idle,MPos:0.000,0.000,0.000,WPos:0.000,0.000,0.000>
[VER:1.1f.20240701:]
[OPT:V,15,1024]
ok
$0=10
$1=25
$2=0
[PARAM:...
ok
"""

_SAMPLE_READY_TIMEOUT_TEXT = """\
ESP-ROM:esp32
rst:0x1 (POWERON_RESET)
boot:0x13 (SPI_FAST_FLASH_BOOT)
entry 0x40078...
"""


class TestProtocolSmokeCounts(unittest.TestCase):
    def test_ver_param_ok_counts(self) -> None:
        # Regex counting logic over a sample Grbl protocol transcript
        text = _SAMPLE_RESPONSE_TEXT
        ver_hits = len(re.findall(r"\[VER:", text))
        param_hits = len(re.findall(r"\[PARAM", text))
        ok_hits = len(re.findall(r"\bok\b", text))
        self.assertEqual(ver_hits, 1)
        self.assertEqual(param_hits, 1)
        self.assertGreaterEqual(ok_hits, 2)

    def test_no_protocol_response(self) -> None:
        text = _SAMPLE_BOOT_TEXT
        ver_hits = len(re.findall(r"\[VER:", text))
        param_hits = len(re.findall(r"\[PARAM", text))
        ok_hits = len(re.findall(r"\bok\b", text))
        self.assertEqual(ver_hits, 0)
        self.assertEqual(param_hits, 0)
        responded = any(v > 0 for v in (ver_hits, param_hits, ok_hits))
        self.assertFalse(responded)


class TestExitCodeMatrix(unittest.TestCase):
    """Exit code checks via mock subprocess to avoid real QEMU."""

    def _run_with_uart(self, uart_text: str, extra_args: Optional[List[str]] = None) -> int:
        """Run main() with a mocked Popen that returns *uart_text* on stdout."""
        args = extra_args or []

        def _fake_popen(*popen_args: Any, **popen_kwargs: Any) -> mock.MagicMock:
            proc = mock.MagicMock()
            proc.stdout = mock.MagicMock()
            lines = uart_text.splitlines(keepends=True)
            proc.stdout.readline.side_effect = lines + [""] * 500
            proc.stdout.read.return_value = ""
            # Use a counter-based poll to avoid exhausting side_effect
            poll_counter: Dict[str, int] = {"calls": 0}
            def _poll() -> Optional[int]:
                poll_counter["calls"] += 1
                return None if poll_counter["calls"] < 200 else 0
            proc.poll.side_effect = _poll
            proc.stdin = mock.MagicMock()
            proc.returncode = 0
            return proc

        with mock.patch("run_qemu_smoke.find_qemu", return_value=Path(r"C:\fake\qemu-system-xtensa.exe")):
            with mock.patch("run_qemu_smoke.package_root_for", return_value=Path(r"C:\fake")):
                with mock.patch("run_qemu_smoke.subprocess.Popen", side_effect=_fake_popen):
                    with tempfile.TemporaryDirectory() as td:
                        flash = Path(td) / "flash.bin"
                        flash.write_bytes(b"\xff" * 1024)
                        with mock.patch("run_qemu_smoke.RESULTS", Path(td)):
                            exit_code = qemu_main(["--flash", str(flash), "--timeout", "0.5", *args])
        return exit_code

    def test_healthy_boot_exit_0(self) -> None:
        code = self._run_with_uart(_SAMPLE_BOOT_TEXT)
        self.assertEqual(code, 0)

    def test_panic_restart_loop_exempt_exit_0(self) -> None:
        """restart_loop driven by visible panics → experimental pass (exit 0)."""
        code = self._run_with_uart(_SAMPLE_PANIC_TEXT)
        self.assertEqual(code, 0)

    def test_restart_loop_without_panic_exit_1(self) -> None:
        """Silent restart loop (no panic markers) → exit 1."""
        boot = "rst:0x1\nboot:0x13\nentry 0x40078...\nGrbl 1.1\n"
        code = self._run_with_uart(boot * 3)
        self.assertEqual(code, 1)

    def test_ready_timeout_no_panic_exit_1(self) -> None:
        """ready_timeout without panic markers → exit 1."""
        code = self._run_with_uart(_SAMPLE_READY_TIMEOUT_TEXT)
        self.assertEqual(code, 1)

    def test_no_uart_allow_empty_exit_0(self) -> None:
        code = self._run_with_uart("", ["--allow-empty"])
        self.assertEqual(code, 0)

    def test_no_uart_no_allow_exit_1(self) -> None:
        code = self._run_with_uart("")
        self.assertEqual(code, 1)

    def test_require_app_misses_exit_1(self) -> None:
        text = "ESP-ROM\nrst:0x1\nboot:0x13\nentry 0x40078...\n"
        code = self._run_with_uart(text, ["--require-app"])
        self.assertEqual(code, 1)

    def test_require_app_hits_exit_0(self) -> None:
        code = self._run_with_uart(_SAMPLE_BOOT_TEXT, ["--require-app"])
        self.assertEqual(code, 0)

    def test_robust_to_qemu_host_error(self) -> None:
        text = "could not load ELF binary"
        code = self._run_with_uart(text)
        self.assertEqual(code, 1)

    def test_deadline_enforced_when_guest_silent(self) -> None:
        """A silent guest must not hang main() past the deadline (pump-thread reader)."""
        import time as _time

        def _fake_popen(*args: Any, **kwargs: Any) -> mock.MagicMock:
            proc = mock.MagicMock()
            proc.stdout = mock.MagicMock()
            proc.stdout.readline.side_effect = lambda: (_time.sleep(30), "")[1]
            proc.stdout.read.return_value = ""
            proc.poll.return_value = None
            proc.stdin = mock.MagicMock()
            proc.returncode = 0
            return proc

        with mock.patch("run_qemu_smoke.find_qemu", return_value=Path(r"C:\fake\qemu-system-xtensa.exe")):
            with mock.patch("run_qemu_smoke.package_root_for", return_value=Path(r"C:\fake")):
                with mock.patch("run_qemu_smoke.subprocess.Popen", side_effect=_fake_popen):
                    with tempfile.TemporaryDirectory() as td:
                        flash = Path(td) / "flash.bin"
                        flash.write_bytes(b"\xff" * 1024)
                        with mock.patch("run_qemu_smoke.RESULTS", Path(td)):
                            t0 = _time.time()
                            code = qemu_main(["--flash", str(flash), "--timeout", "0.5"])
                            elapsed = _time.time() - t0
        self.assertLess(elapsed, 8.0)
        self.assertEqual(code, 1)  # empty UART

    def test_oracle_pass_with_protocol_responded_exit_0(self) -> None:
        """Healthy boot with Grbl protocol responses → exit 0, oracle pass."""
        text = _SAMPLE_BOOT_TEXT + "\n" + _SAMPLE_RESPONSE_TEXT
        code = self._run_with_uart(text)
        self.assertEqual(code, 0)

    def test_brownout_single_boot_not_exempted_exit_1(self) -> None:
        """Non-panic fatal (brownout) must fail even without restart_loop."""
        text = (
            "rst:0x1\nboot:0x13\nentry 0x40078...\nGrbl 1.1\n"
            "Brownout detector was triggered\n"
        )
        code = self._run_with_uart(text)
        self.assertEqual(code, 1)


class TestReportFields(unittest.TestCase):
    def test_report_contains_all_new_fields(self) -> None:
        """Verify protocol_smoke and startup_oracle in report JSON."""

        def _fake_popen(*args: Any, **kwargs: Any) -> mock.MagicMock:
            proc = mock.MagicMock()
            proc.stdout = mock.MagicMock()
            lines = (_SAMPLE_BOOT_TEXT + _SAMPLE_RESPONSE_TEXT).splitlines(keepends=True)
            proc.stdout.readline.side_effect = lines + [""] * 500
            proc.stdout.read.return_value = ""
            _pc: Dict[str, int] = {"calls": 0}
            def _poll() -> Optional[int]:
                _pc["calls"] += 1
                return None if _pc["calls"] < 200 else 0
            proc.poll.side_effect = _poll
            proc.stdin = mock.MagicMock()
            proc.returncode = 0
            return proc

        with mock.patch("run_qemu_smoke.find_qemu", return_value=Path(r"C:\fake\qemu-system-xtensa.exe")):
            with mock.patch("run_qemu_smoke.package_root_for", return_value=Path(r"C:\fake")):
                with mock.patch("run_qemu_smoke.subprocess.Popen", side_effect=_fake_popen):
                    with tempfile.TemporaryDirectory() as td:
                        flash = Path(td) / "flash.bin"
                        flash.write_bytes(b"\xff" * 1024)
                        with mock.patch("run_qemu_smoke.RESULTS", Path(td)):
                            qemu_main(["--flash", str(flash), "--timeout", "0.5", "--interactive"])
                        report_path = Path(td) / "qemu_smoke_report.json"
                        self.assertTrue(report_path.is_file(), f"report missing at {report_path}")
                        data = json.loads(report_path.read_text(encoding="utf-8"))

        # Check new fields
        self.assertIn("protocol_smoke", data, "protocol_smoke missing")
        ps = data["protocol_smoke"]
        self.assertIn("sent", ps)
        self.assertIn("hits", ps)
        self.assertIn("responded", ps)
        self.assertIsInstance(ps["hits"], dict)
        self.assertIn("startup_oracle", data, "startup_oracle missing")
        so = data["startup_oracle"]
        self.assertIn("status", so)
        self.assertIn("fatal_events", so)

        # Check claims_forbidden unchanged
        self.assertIn("claims_forbidden", data)
        self.assertIn("arduino_app_stable_under_qemu", data["claims_forbidden"])

    def test_non_interactive_skips_protocol_smoke(self) -> None:
        """With --no-interactive, interactive_sent should be empty."""

        def _fake_popen(*args: Any, **kwargs: Any) -> mock.MagicMock:
            proc = mock.MagicMock()
            proc.stdout = mock.MagicMock()
            proc.stdout.readline.side_effect = ["line1\n", ""] * 200
            proc.stdout.read.return_value = ""
            _pc2: Dict[str, int] = {"calls": 0}
            def _poll2() -> Optional[int]:
                _pc2["calls"] += 1
                return None if _pc2["calls"] < 200 else 0
            proc.poll.side_effect = _poll2
            proc.stdin = mock.MagicMock()
            proc.returncode = 0
            return proc

        with mock.patch("run_qemu_smoke.find_qemu", return_value=Path(r"C:\fake\qemu-system-xtensa.exe")):
            with mock.patch("run_qemu_smoke.package_root_for", return_value=Path(r"C:\fake")):
                with mock.patch("run_qemu_smoke.subprocess.Popen", side_effect=_fake_popen):
                    with tempfile.TemporaryDirectory() as td:
                        flash = Path(td) / "flash.bin"
                        flash.write_bytes(b"\xff" * 1024)
                        with mock.patch("run_qemu_smoke.RESULTS", Path(td)):
                            qemu_main(["--flash", str(flash), "--timeout", "0.5", "--no-interactive"])
                        report_path = Path(td) / "qemu_smoke_report.json"
                        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("interactive_sent", []), [])
        self.assertEqual(data["protocol_smoke"]["sent"], [])


class TestReadyMarker(unittest.TestCase):
    def test_custom_ready_marker(self) -> None:
        """--ready-marker 'Grbl 1.1' should accept text with that marker."""
        text = "rst:0x1\nboot:0x13\nentry 0x40078...\nGrbl 1.1 ['$' for help]\n"
        from startup_log_oracle import analyze_startup_log
        verdict = analyze_startup_log(text, ready_markers=["Grbl 1.1"])
        self.assertEqual(verdict["status"], "pass")


class TestBannerTriggeredSend(unittest.TestCase):
    def test_banner_pulls_send_before_fixed_schedule(self) -> None:
        """Grbl banner sighting triggers protocol probes before the 2s schedule."""

        def _fake_popen(*args: Any, **kwargs: Any) -> mock.MagicMock:
            proc = mock.MagicMock()
            proc.stdout = mock.MagicMock()
            lines = _SAMPLE_BOOT_TEXT.splitlines(keepends=True)
            proc.stdout.readline.side_effect = lines + [""] * 500
            proc.stdout.read.return_value = ""
            _pc: Dict[str, int] = {"calls": 0}
            def _poll() -> Optional[int]:
                _pc["calls"] += 1
                return None if _pc["calls"] < 200 else 0
            proc.poll.side_effect = _poll
            proc.stdin = mock.MagicMock()
            proc.returncode = 0
            return proc

        with mock.patch("run_qemu_smoke.find_qemu", return_value=Path(r"C:\fake\qemu-system-xtensa.exe")):
            with mock.patch("run_qemu_smoke.package_root_for", return_value=Path(r"C:\fake")):
                with mock.patch("run_qemu_smoke.subprocess.Popen", side_effect=_fake_popen):
                    with tempfile.TemporaryDirectory() as td:
                        flash = Path(td) / "flash.bin"
                        flash.write_bytes(b"\xff" * 1024)
                        with mock.patch("run_qemu_smoke.RESULTS", Path(td)):
                            # 0.5s deadline < 2s fixed schedule: sends only
                            # happen if the banner trigger fires.
                            qemu_main(["--flash", str(flash), "--timeout", "0.5"])
                        data = json.loads((Path(td) / "qemu_smoke_report.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["interactive_sent"]), 1)


if __name__ == "__main__":
    unittest.main()
