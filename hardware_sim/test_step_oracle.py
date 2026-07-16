#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for step_oracle (no sim required)."""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step_oracle import (
    assert_travel_mm,
    max_abs_steps,
    mm_from_steps,
    parse_step_log,
    per_move_delta,
    snapshot_last_steps,
    steps_delta,
    wait_snapshot_settled,
    window_travel_steps,
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

    def test_per_move_and_window(self) -> None:
        self.assertEqual(per_move_delta((0, 0, 0, 0), (2500, 1250, 0, 0))[1], 1250)
        text = "    1.0 0, 0, 0, 0\n    1.5 2500, 0, 0, 0\n    2.0 2500, 0, 0, 0\n"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "w.log"
            p.write_text(text, encoding="utf-8")
            s = parse_step_log(p)
        self.assertEqual(window_travel_steps(s, 1.0, 1.6)[0], 2500)

    def test_wait_snapshot_settled_observes_delayed_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "delayed.log"
            path.write_text("    1.0 0, 0, 0, 0\n", encoding="utf-8")

            def append_later() -> None:
                time.sleep(0.08)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("    2.0 2500, 0, 0, 0\n")

            writer = threading.Thread(target=append_later)
            writer.start()
            snapshot = wait_snapshot_settled(
                path,
                before=(0, 0, 0, 0),
                require_change=True,
                timeout_s=1.0,
                min_wait_s=0.05,
                settle_s=0.05,
                poll_s=0.01,
            )
            writer.join()
        self.assertEqual(snapshot[0], 2500)

    def test_last_snapshot_tracks_reverse_move_below_prior_max(self) -> None:
        text = "    1.0 5000, 0, 0, 0\n    2.0 4000, 0, 0, 0\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "reverse.log"
            path.write_text(text, encoding="utf-8")
            snapshot = snapshot_last_steps(path)
        self.assertEqual(snapshot[0], 4000)
        self.assertEqual(per_move_delta((5000, 0, 0, 0), snapshot)[0], -1000)


if __name__ == "__main__":
    unittest.main()
