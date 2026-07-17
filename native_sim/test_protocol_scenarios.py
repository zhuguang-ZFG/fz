#!/usr/bin/env python3
from __future__ import annotations

import unittest

from run_protocol_scenarios import evaluate
from scenario_contract import minimize_lines, validate_scenario


class TestProtocolScenarios(unittest.TestCase):
    def test_schema_rejects_unknown_expectation_and_bad_boolean(self) -> None:
        errors = validate_scenario(
            {
                "name": "bad",
                "paper_running": "yes",
                "lines": ["G1 X1"],
                "expect": [{"unknown": True}],
            }
        )
        self.assertTrue(any("paper_running must be boolean" in item for item in errors))
        self.assertTrue(any("unknown field unknown" in item for item in errors))

    def test_delta_debugging_keeps_minimal_failure_trigger(self) -> None:
        lines = ["G90", "G1 X1", "X2", "G80", "X3"]
        minimal = minimize_lines(lines, lambda candidate: "G1 X1" in candidate and "X2" in candidate)
        self.assertEqual(minimal, ["G1 X1", "X2"])

    def test_oracle_reports_field_level_mismatch(self) -> None:
        data = {"lines": ["X2"], "expect": [{"motion_line": True, "defer_motion": True}]}
        trace = {"lines": [{"line": "X2", "motion_line": False, "defer_motion": True}]}
        failures = evaluate(data, trace)
        self.assertEqual(len(failures), 1)
        self.assertEqual(
            failures[0]["mismatches"]["motion_line"],
            {"expected": True, "actual": False},
        )


if __name__ == "__main__":
    unittest.main()
