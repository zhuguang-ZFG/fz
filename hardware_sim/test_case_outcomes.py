"""跳过用例不增加通过数，同时不能被失败重跑器误选。"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from dataclasses import asdict

ROOT = Path(os.environ.get("FZ_TEST_ROOT", Path(__file__).resolve().parents[1]))
sys.path[:0] = [str(ROOT), str(ROOT / "hardware_sim")]
import case_runner
import run_hw_sim


class CaseOutcomeTests(unittest.TestCase):
    def test_json_skip_does_not_count_as_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(json.dumps({"time_factor_min": 0.5}))
            result = case_runner.run_json_case(Mock(), path, time_factor=0)
        self.assertIsNone(result.passed)
        self.assertTrue(result.skipped)

    def test_builtin_skip_does_not_count_as_pass(self):
        result = run_hw_sim.run_feed_hold_plant(Mock(), 0)
        self.assertIsNone(result.passed)
        self.assertTrue(result.skipped)

    def test_counts_distinguish_legacy_and_current_skips(self):
        from sim_common.case_result import case_counts
        rows = [{"passed": True}, {"passed": False},
                {"passed": None, "skipped": True}, {"passed": True, "detail": "skipped (need time_factor)"},
                {"name": "session_meta_skipped", "passed": True}]
        self.assertEqual(case_counts(rows), {"passed": 1, "failed": 1, "skipped": 3, "executed": 2, "total": 5})

    def test_null_without_skip_is_failure(self):
        from sim_common.case_result import case_status
        self.assertEqual(case_status({"passed": None}), "fail")

    def test_skipped_result_cannot_keep_passed_true(self):
        for factory in (case_runner.CaseResult, run_hw_sim.CaseResult):
            with self.subTest(factory=factory):
                result = factory("example", True, skipped=True)
                self.assertIsNone(asdict(result)["passed"])

    def test_observe_counts_skips_without_hard_failure(self):
        spec = importlib.util.spec_from_file_location("observe_outcomes", ROOT / "scripts/agent_observe.py")
        observe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(observe)
        reports = {"agent_gate_last.json": {"overall_status": "pass", "profile": "standard",
                   "layers": [{"id": "hardware", "status": "pass"}, {"id": "wokwi_startup", "status": "skip"}]},
                   "last_hw_report.json": {"cases": [{"passed": True}, {"passed": None, "skipped": True},
                                            {"passed": True, "detail": "skipped (legacy)"}]}}
        with patch.object(observe, "_read_json", side_effect=lambda path: reports.get(path.name, {})):
            report = observe.build_observe()
        counts = report["summary"]["hardware_case_counts"]
        self.assertEqual(counts, {"passed": 1, "failed": 0, "skipped": 2, "executed": 1, "total": 3})
        self.assertFalse(report["summary"]["agent_should_block_done_claim"], [item for item in report["findings"] if item["severity"] == "hard"])
        stats = next(item for item in report["findings"] if item["category"] == "hardware_stats")
        self.assertEqual(stats["severity"], "info")

    def test_observe_running_report_blocks_done_claim(self):
        spec = importlib.util.spec_from_file_location("observe_running", ROOT / "scripts/agent_observe.py")
        observe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(observe)
        with patch.object(observe, "_read_json", side_effect=lambda path: {"overall_status": "running", "run_state": "running"} if path.name == "agent_gate_last.json" else {}):
            report = observe.build_observe()
        self.assertTrue(report["summary"]["agent_should_block_done_claim"])


if __name__ == "__main__":
    unittest.main()
