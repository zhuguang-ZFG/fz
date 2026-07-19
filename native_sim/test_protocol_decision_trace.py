#!/usr/bin/env python3
from __future__ import annotations

import os
import unittest
from pathlib import Path

import run_protocol_decision_trace as trace


GRBL_ROOT = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))


class TestProtocolDecisionTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = trace.run_trace(
            [
                "G0 X1",
                "g 01 X1 F100",
                "G2 X1 Y1 I1 J0",
                "G03 X1 Y1 I0 J1",
                "N10 G1 X2 F100",
                "G90 G1 X3 F100",
                "(G1 X9) G92 X0",
                "X4",
                "G10 L2 P1 X0",
                "G20",
                "G38.2 Z-1 F10",
                "G92 X0",
                "$H",
            ],
            GRBL_ROOT.resolve(),
            paper_running=True,
            modal_motion_active=True,
            now_ms=100,
            last_notice_ms=0xFFFFF442,
        )

    def test_only_g0_through_g3_are_motion(self) -> None:
        decisions = {item["line"]: item for item in self.report["lines"]}
        for line in (
            "G0 X1",
            "g 01 X1 F100",
            "G2 X1 Y1 I1 J0",
            "G03 X1 Y1 I0 J1",
            "N10 G1 X2 F100",
            "G90 G1 X3 F100",
        ):
            self.assertTrue(decisions[line]["motion_g0_g3"], line)
            self.assertTrue(decisions[line]["motion_line"], line)
            self.assertTrue(decisions[line]["defer_motion"], line)
        for line in ("G10 L2 P1 X0", "G20", "G92 X0", "(G1 X9) G92 X0"):
            self.assertFalse(decisions[line]["motion_g0_g3"], line)
            self.assertFalse(decisions[line]["motion_line"], line)
            self.assertFalse(decisions[line]["defer_motion"], line)
        # G38 / $H are not is_motion_line, but must defer during paper change (fail-closed).
        for line in ("G38.2 Z-1 F10", "$H"):
            self.assertFalse(decisions[line]["motion_g0_g3"], line)
            self.assertFalse(decisions[line]["motion_line"], line)
            self.assertTrue(decisions[line]["defer_motion"], line)

    def test_modal_axis_only_line_is_motion(self) -> None:
        decisions = {item["line"]: item for item in self.report["lines"]}
        self.assertFalse(decisions["X4"]['motion_g0_g3'])
        self.assertTrue(decisions["X4"]['motion_line'])
        self.assertTrue(decisions["X4"]['defer_motion'])

    def test_modal_setting_with_axis_is_motion_but_coordinate_set_is_not(self) -> None:
        report = trace.run_trace(
            ["G1 X1", "G91 X2", "G20 Y1", "G93 Z1 F2", "G10 L2 P1 X0", "G92 X0", "G28 X0"],
            GRBL_ROOT.resolve(),
            paper_running=True,
            stateful_modal=True,
        )
        decisions = {item["line"]: item for item in report["lines"]}
        for line in ("G91 X2", "G20 Y1", "G93 Z1 F2"):
            self.assertTrue(decisions[line]["motion_line"], line)
            self.assertTrue(decisions[line]["defer_motion"], line)
        for line in ("G10 L2 P1 X0", "G92 X0"):
            self.assertFalse(decisions[line]["motion_line"], line)
            self.assertFalse(decisions[line]["defer_motion"], line)
        # G28 is not motion_line for modal/license policy, but defers while paper runs.
        self.assertFalse(decisions["G28 X0"]["motion_line"])
        self.assertTrue(decisions["G28 X0"]["defer_motion"])
    def test_notice_interval_is_wrap_safe(self) -> None:
        self.assertTrue(self.report["notice"]["notice_due"])

    def test_stateful_modal_sequence(self) -> None:
        report = trace.run_trace(
            ["G1 X1 F100", "X2", "G10 L2 P1 X0", "X3", "G80", "X4"],
            GRBL_ROOT.resolve(),
            paper_running=True,
            stateful_modal=True,
        )
        decisions = {item["line"]: item for item in report["lines"]}
        self.assertFalse(decisions["G1 X1 F100"]["modal_before"])
        self.assertTrue(decisions["G1 X1 F100"]["modal_after"])
        self.assertTrue(decisions["X2"]["defer_motion"])
        self.assertFalse(decisions["G10 L2 P1 X0"]["defer_motion"])
        self.assertTrue(decisions["G10 L2 P1 X0"]["modal_after"])
        self.assertTrue(decisions["X3"]["defer_motion"])
        self.assertFalse(decisions["G80"]["modal_after"])
        self.assertFalse(decisions["X4"]["defer_motion"])

if __name__ == "__main__":
    unittest.main()
