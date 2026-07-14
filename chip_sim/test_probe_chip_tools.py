#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestChipProbe(unittest.TestCase):
    def test_probe_exit_0(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "chip_sim" / "probe_chip_tools.py")],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        self.assertIn("chip_sim probe", r.stdout)

    def test_require_any_may_fail(self) -> None:
        r = subprocess.run(
            [
                sys.executable,
                str(FZ / "chip_sim" / "probe_chip_tools.py"),
                "--require-any",
            ],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        # 0 if tools installed; 2 if not — both valid
        self.assertIn(r.returncode, (0, 2))


if __name__ == "__main__":
    unittest.main()
