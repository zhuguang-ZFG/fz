"""trace不完整必须判负，且不能被字段缩减器吞掉。"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_protocol_scenarios as runner


class TraceShapeTest(unittest.TestCase):
    def setUp(self):
        self.data = {"name": "trace-test", "lines": ["G90", "G1 X1"],
                     "expect": [{"motion_line": False}, {"motion_line": True}]}

    def test_truncated_trace_is_not_pass(self):
        for trace in ([], [{"motion_line": False}]):
            with self.subTest(trace=trace):
                failures = runner.evaluate(self.data, trace)
                self.assertTrue(failures)
                self.assertEqual(failures[0]["kind"], "trace_length")

    def test_surplus_trace_is_not_pass(self):
        failures = runner.evaluate(self.data, [{"motion_line": False}, {"motion_line": True}, {}])
        self.assertTrue(failures)
        self.assertEqual(failures[0]["kind"], "trace_length")

    def test_bad_container_is_structured_failure(self):
        for trace in (None, {}, {"lines": None}, "bad", 1):
            with self.subTest(trace=trace):
                failures = runner.evaluate(self.data, trace)
                self.assertTrue(failures)
                self.assertEqual(failures[0]["kind"], "trace_shape")

    def test_non_object_row_is_structured_failure(self):
        failures = runner.evaluate(self.data, [{"motion_line": False}, None])
        self.assertTrue(failures)
        self.assertEqual(failures[0]["kind"], "trace_shape")

    def test_input_and_expectation_counts_must_match(self):
        self.data["lines"].append("G80")
        self.assertTrue(runner.evaluate(self.data, [{"motion_line": False}, {"motion_line": True}]))

    def test_list_and_envelope_match(self):
        rows = [{"motion_line": False}, {"motion_line": True}]
        self.assertEqual(runner.evaluate(self.data, rows), [])
        self.assertEqual(runner.evaluate(self.data, {"lines": rows}), [])

    def test_field_mismatch_remains_precise(self):
        failures = runner.evaluate(self.data, [{"motion_line": False}, {"motion_line": False}])
        self.assertEqual(failures[0]["index"], 1)
        self.assertEqual(failures[0]["line"], "G1 X1")
        self.assertEqual(failures[0]["mismatches"]["motion_line"], {"expected": True, "actual": False})

    def test_bad_trace_does_not_enter_field_minimizer(self):
        for trace in ([{"motion_line": False}], None):
            with self.subTest(trace=trace), patch.object(runner, "load_scenario", return_value=self.data), \
                    patch.object(runner, "trace_for", return_value=trace), \
                    patch.object(runner, "minimize_failure", side_effect=AssertionError("不得缩减缺失trace")):
                result = runner.run_scenario(runner.HERE / "scenarios" / "fixture.json", Path("unused"))
                self.assertEqual(result["status"], "fail")
                self.assertNotIn("minimal_regression_case", result)

    def test_field_minimization_does_not_accept_a_broken_trace(self):
        failure = {"line": "G1 X1", "mismatches": {"motion_line": {"expected": True, "actual": False}}}
        with patch.object(runner, "trace_for", return_value={"lines": []}):
            result = runner.minimize_failure(self.data, Path("unused"), failure)
        self.assertEqual(result, self.data["lines"])


if __name__ == "__main__": unittest.main()
