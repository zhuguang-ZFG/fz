#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

FZ = Path(__file__).resolve().parent.parent


class TestAgentGate(unittest.TestCase):
    def test_contract(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "agent_gate.py"), "--print-contract"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("agent_gate", r.stdout.lower())

    def test_quick_profile(self) -> None:
        r = subprocess.run(
            [
                sys.executable,
                str(FZ / "scripts" / "agent_gate.py"),
                "--profile",
                "quick",
            ],
            cwd=str(FZ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=420,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout[-2000:] + r.stderr[-1000:])
        rep = FZ / "results" / "agent_gate_last.json"
        self.assertTrue(rep.is_file())
        data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(data["suite"], "agent_gate")
        self.assertEqual(data["overall_status"], "pass")
        self.assertIn("agent_hints", data)
        hw = [x for x in data["layers"] if x["id"] == "hardware"][0]
        self.assertEqual(hw["status"], "skip")

class TestAgentGateQemuLayer(unittest.TestCase):
    """Hermetic in-process tests for the qemu_startup layer (no real QEMU/firmware)."""

    @classmethod
    def setUpClass(cls) -> None:
        chip_sim = str(FZ / "chip_sim")
        if chip_sim not in sys.path:
            sys.path.insert(0, chip_sim)

    def _invoke_gate(self, tmp: Path, argv_extra: list, find_qemu_value: Any, make_flash: bool = False, fail_build: bool = False) -> dict:
        import scripts.agent_gate as ag

        report = tmp / "gate.json"
        results = tmp / "results"
        (results / "qemu").mkdir(parents=True)
        if make_flash:
            (results / "qemu" / "flash_image_4mb.bin").write_bytes(b"\xff")
        if fail_build:
            def _run_se(cmd: list, *args: Any, **kwargs: Any) -> tuple:
                if any("build_flash_image" in str(part) for part in cmd):
                    return (1, 0.1)
                return (0, 0.1)
            run_patcher = mock.patch.object(ag, "_run", side_effect=_run_se)
        else:
            run_patcher = mock.patch.object(ag, "_run", return_value=(0, 0.1))
        with mock.patch("run_qemu_smoke.find_qemu", return_value=find_qemu_value):
            with run_patcher, mock.patch.object(ag, "RESULTS", results):
                saved = sys.argv
                try:
                    sys.argv = ["agent_gate.py", "--profile", "quick", "--json-out", str(report), "--no-shared-sim", *argv_extra]
                    exit_code = ag.main()
                finally:
                    sys.argv = saved
        self.assertEqual(exit_code, 0)
        data = json.loads(report.read_text(encoding="utf-8"))
        layers = [x for x in data["layers"] if x["id"] == "qemu_startup"]
        self.assertEqual(len(layers), 1)
        return layers[0]

    def test_qemu_startup_skip_no_grbl(self) -> None:
        """grbl_root unavailable → qemu_startup skips (even with qemu present)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            layer = self._invoke_gate(
                tmp,
                ["--grbl-root", str(tmp / "missing-grbl")],
                Path(r"C:\fake\qemu-system-xtensa.exe"),
            )
        self.assertEqual(layer["status"], "skip")

    def test_qemu_startup_skip_no_qemu(self) -> None:
        """grbl_root present but no qemu binary → qemu_startup skips."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            layer = self._invoke_gate(tmp, ["--grbl-root", str(tmp)], None)
        self.assertEqual(layer["status"], "skip")

    def test_qemu_startup_run_branch_pass(self) -> None:
        """qemu + flash image present, _run succeeds → qemu_startup pass."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            layer = self._invoke_gate(
                tmp,
                ["--grbl-root", str(tmp)],
                Path(r"C:\fake\qemu-system-xtensa.exe"),
                make_flash=True,
            )
        self.assertEqual(layer["status"], "pass")
        self.assertEqual(layer["exit_code"], 0)

    def test_qemu_startup_build_failure_skips(self) -> None:
        """flash image build fails → layer skips honestly (no silent pass)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            layer = self._invoke_gate(
                tmp,
                ["--grbl-root", str(tmp)],
                Path(r"C:\fake\qemu-system-xtensa.exe"),
                fail_build=True,
            )
        self.assertEqual(layer["status"], "skip")


if __name__ == "__main__":
    unittest.main()
