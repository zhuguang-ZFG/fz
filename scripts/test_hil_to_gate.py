#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for hil_to_gate (no serial hardware)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestHilToGateOffline(unittest.TestCase):
    def test_offline_help(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "hil_to_gate.py"), "--help"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("--port", r.stdout)

    def test_offline_skip_smoke(self) -> None:
        r = subprocess.run(
            [
                sys.executable,
                str(FZ / "scripts" / "hil_to_gate.py"),
                "--skip-smoke",
            ],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        self.assertIn("OFFLINE", r.stdout)


class TestTemplateStrictMarkers(unittest.TestCase):
    def test_template_has_gates_fence(self) -> None:
        text = (FZ / "a2a_workorders" / "TEMPLATE.md").read_text(encoding="utf-8")
        self.assertIn("```gates", text)
        self.assertRegex(text, r"\brisk\s*[:=]")
        self.assertRegex(text, r"(?im)^\s*owns\s*:")


if __name__ == "__main__":
    unittest.main()
