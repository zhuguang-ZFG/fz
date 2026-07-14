#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestAgentObserve(unittest.TestCase):
    def test_cli(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "agent_observe.py"), "--quiet"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        # 0 green hard-free, 1 if hard findings
        self.assertIn(r.returncode, (0, 1), msg=r.stdout + r.stderr)
        js = FZ / "results" / "agent_observe_last.json"
        md = FZ / "results" / "agent_observe_last.md"
        self.assertTrue(js.is_file())
        self.assertTrue(md.is_file())
        data = json.loads(js.read_text(encoding="utf-8"))
        self.assertEqual(data.get("suite"), "agent_observe")
        self.assertIn("findings", data)
        self.assertIn("next_actions", data)
        self.assertTrue(len(data["findings"]) >= 1)
        self.assertIn("Agent observe", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
