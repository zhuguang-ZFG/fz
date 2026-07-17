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
        self.assertGreaterEqual(int(data.get("version") or 0), 3)
        self.assertIn("summary", data)
        self.assertIn("agent_should_prefer_standard", data["summary"])
        self.assertIn("soft_files_with_errors", data["summary"])
        self.assertIn("hardware_cases_in_last_report", data["summary"])

    def test_allowlisted_divergence_helper(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(mod._is_allowlisted("soft:parsetest.nc", {"soft:parsetest.nc"}))
        self.assertFalse(mod._is_allowlisted("soft:new_unknown.nc", {"soft:parsetest.nc"}))

    def test_fail_without_golden_helper(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        missing = mod._fail_stems_without_golden()
        self.assertIsInstance(missing, list)

    def test_paper_interaction_failure_surfaces_minimal_config(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        finding = mod._paper_interaction_finding(
            {
                "status": "fail",
                "minimal_failure": {
                    "config": {"paper": "missing", "drive": "normal"},
                    "violations": ["unsafe_or_missing_completion"],
                },
            }
        )
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "hard")
        self.assertIn("missing", finding["detail"])
        self.assertEqual(finding["action"], "python hardware_sim/run_paper_plant_interactions.py")


if __name__ == "__main__":
    unittest.main()
