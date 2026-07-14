#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for win_full_sim preflight helpers."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestWinFullSim(unittest.TestCase):
    def test_help(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "win_full_sim.py"), "--help"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("Windows", r.stdout)

    def test_preflight_import(self) -> None:
        sys.path.insert(0, str(FZ / "scripts"))
        import win_full_sim as w  # type: ignore

        pf = w.preflight()
        self.assertEqual(pf.id, "L0")
        self.assertIn(pf.status, ("pass", "fail"))


if __name__ == "__main__":
    unittest.main()
