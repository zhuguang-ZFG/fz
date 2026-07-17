#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

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
            timeout=180,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout[-2000:] + r.stderr[-1000:])
        rep = FZ / "results" / "agent_gate_last.json"
        self.assertTrue(rep.is_file())
        data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(data["suite"], "agent_gate")
        self.assertEqual(data["overall_status"], "pass")
        self.assertIn("agent_hints", data)
        # hardware should be skipped on quick
        hw = [x for x in data["layers"] if x["id"] == "hardware"][0]
        self.assertEqual(hw["status"], "skip")


if __name__ == "__main__":
    unittest.main()
