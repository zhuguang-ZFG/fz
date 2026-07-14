#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestSimRerun(unittest.TestCase):
    def test_list_exit_0(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "sim_rerun.py"), "--list"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("protocol_failed", r.stdout)

    def test_help(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "sim_rerun.py"), "--help"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
