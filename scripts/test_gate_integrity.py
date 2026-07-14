#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R19: gate integrity — inject packs must go red; golden pack must go green.

Proves the protocol harness cannot silent-false-green on known bad expects.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent
REG = FZ / "protocol_sim" / "run_regression.py"


class TestGateIntegrity(unittest.TestCase):
    def test_inject_packs_exist(self) -> None:
        inject = FZ / "protocol_sim" / "cases" / "inject"
        files = list(inject.glob("*.json"))
        self.assertGreaterEqual(len(files), 3, msg="need >=3 inject false-green packs")

    def test_golden_packs_exist(self) -> None:
        golden = FZ / "protocol_sim" / "cases" / "golden"
        files = list(golden.glob("*.json"))
        self.assertGreaterEqual(len(files), 5, msg="need >=5 golden contracts")

    def test_integrity_inject_must_pass(self) -> None:
        """All inject cases fail as normal → integrity exit 0."""
        r = subprocess.run(
            [sys.executable, str(REG), "--start-sim", "--integrity-inject"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            r.returncode,
            0,
            msg=(r.stdout[-2500:] + "\n" + r.stderr[-1500:]),
        )
        rep = FZ / "protocol_sim" / "results" / "integrity_inject_last.json"
        self.assertTrue(rep.is_file())
        data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertTrue(data.get("passed"))
        self.assertEqual(int(data.get("n_leaked_false_green") or 0), 0)
        self.assertGreaterEqual(int(data.get("n_red_as_expected") or 0), 3)

    def test_golden_suite_must_pass(self) -> None:
        r = subprocess.run(
            [sys.executable, str(REG), "--start-sim", "--golden"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            r.returncode,
            0,
            msg=(r.stdout[-2500:] + "\n" + r.stderr[-1500:]),
        )
        gold = FZ / "protocol_sim" / "results" / "golden_last.json"
        self.assertTrue(gold.is_file())
        data = json.loads(gold.read_text(encoding="utf-8"))
        self.assertTrue(data.get("passed"))
        self.assertGreaterEqual(int(data.get("n") or 0), 5)


if __name__ == "__main__":
    unittest.main()
