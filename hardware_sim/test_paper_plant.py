#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_plant import FaultProfile, PaperPlantConfig, VirtualClock, simulate  # noqa: E402
from run_paper_plant_campaign import REQUIRED_COVERAGE, run_campaign  # noqa: E402


class TestPaperPlant(unittest.TestCase):
    def test_virtual_clock_preserves_timestamp_insertion_order(self) -> None:
        clock = VirtualClock()
        seen: list[str] = []
        clock.schedule(20, lambda: seen.append("late"))
        clock.schedule(10, lambda: seen.append("first"))
        clock.schedule(10, lambda: seen.append("second"))
        clock.run(20)
        self.assertEqual(seen, ["first", "second", "late"])
        self.assertEqual(clock.now_ms, 20)

    def test_virtual_clock_advances_across_idle_time(self) -> None:
        clock = VirtualClock()
        clock.run(25)
        self.assertEqual(clock.now_ms, 25)

    def test_nominal_positions_paper_without_wall_clock_sleep(self) -> None:
        result = simulate(PaperPlantConfig(), FaultProfile(name="nominal"))
        self.assertEqual(result["outcome"], "completed")
        self.assertEqual(result["reason"], "paper_positioned")
        self.assertLess(result["virtual_duration_ms"], 2500)
        self.assertIn("sensor_debounce", result["covered"])
        self.assertIn("overtravel_complete", result["covered"])

    def test_jam_fails_closed_at_timeout(self) -> None:
        result = simulate(PaperPlantConfig(), FaultProfile(name="jam", jam_at_mm=25.0))
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["reason"], "timeout")
        self.assertIn("motor_jam", result["covered"])

    def test_stuck_active_sensor_is_rejected_as_implausible(self) -> None:
        result = simulate(PaperPlantConfig(), FaultProfile(name="stuck", sensor_stuck=True))
        self.assertEqual(result["reason"], "sensor_active_too_early")
        self.assertIn("sensor_plausibility", result["covered"])

    def test_full_campaign_closes_required_fault_coverage(self) -> None:
        report = run_campaign()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["coverage"]["missing"], [])
        self.assertEqual(set(report["coverage"]["covered"]), REQUIRED_COVERAGE)


if __name__ == "__main__":
    unittest.main()
