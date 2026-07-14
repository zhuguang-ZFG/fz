#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for case_runner helpers (no sim)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_runner import _match_expect, load_case_files  # noqa: E402
from step_oracle import per_move_delta, snapshot_max_abs, window_travel_steps, parse_step_log  # noqa: E402


class TestCaseRunnerUnit(unittest.TestCase):
    def test_match_expect(self) -> None:
        self.assertTrue(_match_expect(["ok"], "ok"))
        self.assertTrue(_match_expect(["error:22"], "error"))
        self.assertTrue(_match_expect(["ALARM:1"], "error_or_alarm"))
        self.assertTrue(_match_expect(["<Idle|MPos:0,0,0>"], "status"))

    def test_load_cases(self) -> None:
        cases = load_case_files(Path(__file__).resolve().parent / "cases")
        self.assertGreaterEqual(len(cases), 3)
        names = {p.stem for p in cases}
        self.assertIn("move_x10_step_window", names)

    def test_per_move_delta(self) -> None:
        d = per_move_delta((100, 0, 0, 0), (2600, 0, 0, 0))
        self.assertEqual(d[0], 2500)

    def test_window_travel(self) -> None:
        text = """    1.0 0, 0, 0, 0
    2.0 2500, 0, 0, 0
    3.0 2500, 1250, 0, 0
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.log"
            p.write_text(text, encoding="utf-8")
            samples = parse_step_log(p)
        d = window_travel_steps(samples, 1.0, 2.5)
        self.assertEqual(d[0], 2500)
        self.assertEqual(max(s.steps[0] for s in samples), 2500)


if __name__ == "__main__":
    unittest.main()
