#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for step_oracle (no sim required)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step_oracle import (
    assert_travel_mm,
    max_abs_steps,
    mm_from_steps,
    parse_step_log,
    steps_delta,
)


class TestStepOracle(unittest.TestCase):
    def test_parse_sample_lines(self) -> None:
        text = """# block number 0
    15.49800 1, 0, 0, 0
    15.51400 2, 0, 0, 0
    20.00000 2500, 0, 0, 0
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.log"
            p.write_text(text, encoding="utf-8")
            samples = parse_step_log(p)
        self.assertEqual(len(samples), 3)
        self.assertEqual(samples[-1].steps[0], 2500)
        self.assertEqual(max_abs_steps(samples)[0], 2500)

    def test_mm_from_steps_250(self) -> None:
        mm = mm_from_steps([2500, 1250, 0], [250.0, 250.0, 250.0])
        self.assertAlmostEqual(mm[0], 10.0)
        self.assertAlmostEqual(mm[1], 5.0)

    def test_assert_travel(self) -> None:
        ok, detail, actual = assert_travel_mm(
            [2500, 0, 0], [10.0, 0.0, 0.0], [250.0, 250.0, 250.0], eps_mm=0.2
        )
        self.assertTrue(ok, detail)
        self.assertAlmostEqual(actual[0], 10.0)

    def test_steps_delta(self) -> None:
        text1 = "    1.0 100, 0, 0, 0\n"
        text2 = "    1.0 100, 0, 0, 0\n    2.0 2600, 0, 0, 0\n"
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.log"
            b = Path(td) / "b.log"
            a.write_text(text1, encoding="utf-8")
            b.write_text(text2, encoding="utf-8")
            d = steps_delta(parse_step_log(a), parse_step_log(b))
        self.assertEqual(d[0], 2500)


if __name__ == "__main__":
    unittest.main()
