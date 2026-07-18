#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "run_product_core_coverage", HERE / "run_product_core_coverage.py"
)
assert SPEC and SPEC.loader
COVERAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COVERAGE)


class TestCoveragePolicy(unittest.TestCase):
    def test_accepts_metrics_at_minimum(self) -> None:
        policy = {"Core.h": {"lines_percent": 95.0, "branches_percent": 80.0}}
        files = {"Core.h": {"lines_percent": 95.0, "branches_percent": 80.0}}
        self.assertEqual(COVERAGE._coverage_violations(files, policy), [])

    def test_reports_regression(self) -> None:
        policy = {"Core.h": {"lines_percent": 95.0}}
        files = {"Core.h": {"lines_percent": 94.99}}
        self.assertEqual(
            COVERAGE._coverage_violations(files, policy),
            [
                {
                    "file": "Core.h",
                    "metric": "lines_percent",
                    "actual": 94.99,
                    "minimum": 95.0,
                    "reason": "below_minimum",
                }
            ],
        )

    def test_does_not_round_a_regression_up_to_minimum(self) -> None:
        actual = COVERAGE._percent(
            {"lines": {"count": 20001, "covered": 19000}}, "lines"
        )
        self.assertLess(actual, 95.0)
        self.assertEqual(
            COVERAGE._coverage_violations(
                {"Core.h": {"lines_percent": actual}},
                {"Core.h": {"lines_percent": 95.0}},
            )[0]["reason"],
            "below_minimum",
        )

    def test_reports_missing_file(self) -> None:
        policy = {"Core.h": {"functions_percent": 100.0}}
        self.assertEqual(
            COVERAGE._coverage_violations({}, policy),
            [{"file": "Core.h", "metric": "file", "reason": "missing"}],
        )

    def test_loads_repository_policy(self) -> None:
        policy = COVERAGE._load_policy(HERE / "coverage_policy.json")
        self.assertIn("PaperSystemCore.h", policy)
        self.assertIn("branches_percent", policy["WebUI/BTStateCore.h"])

    def test_rejects_unknown_metric(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                json.dumps({"files": {"Core.h": {"statements": 90}}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsupported coverage metric"):
                COVERAGE._load_policy(path)

    def test_rejects_boolean_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(
                json.dumps({"files": {"Core.h": {"lines": True}}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "invalid minimum"):
                COVERAGE._load_policy(path)

    def test_invalid_policy_replaces_stale_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy_path = root / "policy.json"
            policy_path.write_text(
                json.dumps({"files": {"Core.h": {"bad": 90}}}), encoding="utf-8"
            )
            results = root / "results"
            results.mkdir()
            report_path = results / "coverage_summary.json"
            report_path.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            with mock.patch.object(COVERAGE, "RESULTS", results):
                with redirect_stderr(io.StringIO()):
                    exit_code = COVERAGE.main(["--policy", str(policy_path)])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 1)
            self.assertEqual(report["status"], "fail")
            self.assertIn("invalid coverage policy", report["stderr"])

    def test_formats_missing_metric_without_crashing(self) -> None:
        self.assertEqual(COVERAGE._display_percent(None), "n/a")

    def _run_main_with_run_result(self, run_result: int, run_stdout: str, directory: str) -> int:
        root = Path(directory)
        results = root / "results"
        results.mkdir()
        policy_path = root / "policy.json"
        policy_path.write_text(
            json.dumps({"files": {"Core.h": {"lines": 80}}}), encoding="utf-8"
        )
        build = mock.Mock(returncode=0, stdout="", stderr="")
        run = mock.Mock(returncode=run_result, stdout=run_stdout, stderr="")
        with mock.patch.object(COVERAGE, "RESULTS", results), mock.patch.object(
            COVERAGE.native_tests, "find_compiler", return_value=(Path("clang++"), "clang")
        ), mock.patch.object(
            COVERAGE, "_tool", side_effect=lambda name, compiler: Path(name)
        ), mock.patch.object(
            COVERAGE, "_runtime_path_entries", return_value=[]
        ), mock.patch.object(
            COVERAGE.subprocess, "run", side_effect=[build, run]
        ):
            with redirect_stderr(io.StringIO()):
                exit_code = COVERAGE.main(["--policy", str(policy_path)])
        self._report = json.loads((results / "coverage_summary.json").read_text(encoding="utf-8"))
        return exit_code

    def test_pre_main_crash_maps_to_env_skip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exit_code = self._run_main_with_run_result(0xC0000005, "", directory)
            self.assertEqual(exit_code, 2)
            self.assertEqual(self._report["status"], "skip")
            self.assertEqual(self._report["run_exit_code"], 0xC0000005)
            self.assertIn("pre-main", self._report["stderr"])

    def test_driver_failure_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            exit_code = self._run_main_with_run_result(1, "seed line printed\n", directory)
            self.assertEqual(exit_code, 1)
            self.assertEqual(self._report["status"], "fail")
            self.assertEqual(self._report["run_exit_code"], 1)


if __name__ == "__main__":
    unittest.main()
