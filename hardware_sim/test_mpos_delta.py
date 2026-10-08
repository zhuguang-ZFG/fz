"""位置差必须来自运动前后的完整Idle帧，错误和空断言不能假通过。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_runner as runner


def idle(x, y=0, z=0):
    values = [x, y, z]
    return values, [f"<Idle|MPos:{x},{y},{z}>"]


class MposDeltaTest(unittest.TestCase):
    def run_case(self, data, samples):
        client = Mock()
        client.send_line.return_value = ["ok"]
        data = {"id": "position-check", "soft_reset": False, **data}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(runner, "wait_idle", side_effect=samples) as waits:
                result = runner.run_json_case(client, path)
            return result, client, waits.call_count

    def test_step_uses_signed_xyz_from_its_own_start(self):
        result, _, calls = self.run_case({"steps": [{"send": "G1 X8 Y25 Z2", "expect_mpos_delta": [-2, 5, -1]}]},
                                         [idle(10, 20, 3), idle(8, 25, 2)])
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(calls, 2)
        self.assertEqual(result.mpos, [8, 25, 2])

    def test_wrong_direction_is_failure(self):
        result, _, _ = self.run_case({"steps": [{"send": "G1 X-10", "expect_mpos_delta": [10, 0, 0]}]},
                                     [idle(0), idle(-10)])
        self.assertFalse(result.passed)
        self.assertIn("mpos_delta", result.detail)

    def test_top_level_compares_whole_case_after_setup(self):
        data = {"setup": ["G90"], "expect_mpos_delta": [8, 2, 0],
                "steps": [{"send": "G1 X18 Y22"}]}
        result, client, calls = self.run_case(data, [idle(10, 20), idle(18, 22)])
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(calls, 2)
        self.assertEqual(client.send_line.call_args_list[0].args[0], "G90")

    def test_whole_case_mismatch_is_failure(self):
        result, _, _ = self.run_case({"expect_mpos_delta": [10, 0, 0], "steps": [{"send": "G1 X1"}]},
                                     [idle(0), idle(1)])
        self.assertFalse(result.passed)

    def test_zero_vector_is_checked(self):
        result, _, _ = self.run_case({"steps": [{"send": "G1 X1", "expect_mpos_delta": [0, 0, 0]}]},
                                     [idle(0), idle(1)])
        self.assertFalse(result.passed)

    def test_each_step_has_its_own_baseline(self):
        data = {"steps": [{"send": "G1 X10", "expect_mpos_delta": [10, 0, 0]},
                          {"send": "G1 X15", "expect_mpos_delta": [5, 0, 0]}]}
        result, _, calls = self.run_case(data, [idle(0), idle(10), idle(10), idle(15)])
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(calls, 4)

    def test_tolerance_and_exact_zero(self):
        for eps, passed in ((0.6, True), (0, False)):
            with self.subTest(eps=eps):
                result, _, _ = self.run_case({"expect_mpos_delta": [10, 0, 0], "eps_mm": eps},
                                             [idle(0), idle(10.25)])
                self.assertEqual(result.passed, passed)

    def test_invalid_expectation_fails_before_io(self):
        for vector in (None, [], [1, 2], [1, 2, 3, 4], [True, 0, 0], [float("nan"), 0, 0], ["1", 0, 0]):
            with self.subTest(vector=vector):
                result, client, calls = self.run_case({"expect_mpos_delta": vector}, [])
                self.assertFalse(result.passed)
                client.send_line.assert_not_called()
                self.assertEqual(calls, 0)

    def test_invalid_tolerance_fails_before_io(self):
        for eps in (-1, float("nan"), float("inf"), True, "1"):
            with self.subTest(eps=eps):
                result, client, _ = self.run_case({"expect_mpos_delta": [0, 0, 0], "eps_mm": eps}, [])
                self.assertFalse(result.passed)
                client.send_line.assert_not_called()

    def test_missing_finite_idle_position_is_failure(self):
        bad = [([0, 0, 0], ["<Run|MPos:0,0,0>"]),
               ([0, 0, 0], ["<Run|MPos:0,0,0>", "<Idle|WPos:0,0,0>"]),
               (None, ["<Idle|MPos:nan,0,0>"]),
               ([0, 0, 0], ["<Idle|MPos:0,0,0junk>"]),
               ([0, 0, 0], ["<Idle|MPos:0,0,0|MPos:1,1,1>"])]
        for sample in bad:
            with self.subTest(sample=sample):
                result, client, _ = self.run_case({"expect_mpos_delta": [0, 0, 0], "steps": [{"send": "G1 X1"}]}, [sample])
                self.assertFalse(result.passed)
                client.send_line.assert_not_called()

    def test_end_position_must_not_be_stale(self):
        result, _, _ = self.run_case({"steps": [{"send": "G1 X10", "expect_mpos_delta": [10, 0, 0]}]},
                                     [idle(0), ([10, 0, 0], ["<Run|MPos:10,0,0>", "<Idle|WPos:10,0,0>"])])
        self.assertFalse(result.passed)

    def test_non_send_step_cannot_silently_ignore_assertion(self):
        result, _, calls = self.run_case({"steps": [{"expect_status": "Idle", "expect_mpos_delta": [0, 0, 0]}]}, [])
        self.assertFalse(result.passed)
        self.assertEqual(calls, 0)

    def test_absent_assertion_keeps_existing_io(self):
        result, client, calls = self.run_case({"steps": [{"send": "G21"}]}, [])
        self.assertTrue(result.passed)
        self.assertEqual(calls, 0)
        client.send_line.assert_called_once()

    def test_async_send_still_checks_completed_delta(self):
        result, client, calls = self.run_case({"steps": [{"send": "G1 X10", "async": True,
            "expect_mpos_delta": [10, 0, 0]}]}, [idle(0), idle(10)])
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(calls, 2)
        client.sock.sendall.assert_called_once_with(b"G1 X10\n")

    def test_case_and_step_assertions_use_separate_baselines(self):
        result, _, calls = self.run_case({"expect_mpos_delta": [10, 0, 0],
            "steps": [{"send": "G1 X15", "expect_mpos_delta": [10, 0, 0]}]},
            [idle(5), idle(5), idle(15), idle(15)])
        self.assertTrue(result.passed, result.detail)
        self.assertEqual(calls, 4)


if __name__ == "__main__": unittest.main()
