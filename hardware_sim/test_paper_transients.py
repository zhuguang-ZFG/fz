#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

from paper_plant import FaultProfile, PaperPlantConfig, PaperTransportSimulation, TransientFault, simulate
import run_paper_transient_campaign as transient_campaign
from run_paper_transient_campaign import run_campaign, shrink_window


class TestPaperTransients(unittest.TestCase):
    def test_campaign_covers_recovery_and_fail_closed_paths(self) -> None:
        report = run_campaign()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(report["cases"]), 6)
        self.assertTrue(all(case["passed"] for case in report["cases"]))
        self.assertTrue(any(case["minimal_failure_window"] for case in report["cases"]))

    def test_brief_jam_records_start_and_end(self) -> None:
        result = simulate(PaperPlantConfig(), FaultProfile(name="brief"), [TransientFault("jam", 300, 500)])
        events = [(item["event"], item.get("kind"), item["at_ms"]) for item in result["transitions"]]
        self.assertIn(("fault_start", "jam", 300), events)
        self.assertIn(("fault_end", "jam", 500), events)
        self.assertEqual(result["outcome"], "completed")

    def test_rejects_invalid_or_overlapping_windows(self) -> None:
        with self.assertRaises(ValueError):
            TransientFault("jam", 100, 100)
        with self.assertRaisesRegex(ValueError, "integer milliseconds"):
            TransientFault("jam", True, 100)
        with self.assertRaisesRegex(ValueError, "does not accept"):
            TransientFault("jam", 0, 100, 1.0)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            TransientFault("speed_scale", 0, 100, float("nan"))
        with self.assertRaisesRegex(ValueError, "overlapping"):
            PaperTransportSimulation(
                PaperPlantConfig(),
                FaultProfile(),
                [TransientFault("sensor", 100, 200, 0.0), TransientFault("sensor", 150, 250, 1.0)],
            )

    def test_shrinker_finds_local_minimum(self) -> None:
        transient = TransientFault("jam", 0, 100)
        minimal = shrink_window(transient, 10, lambda item: item.end_ms - item.start_ms >= 30)
        self.assertEqual(minimal.end_ms - minimal.start_ms, 30)

    def test_incorrect_expectation_must_fail_campaign(self) -> None:
        mutant = (("mutant", (TransientFault("jam", 300, 500),), "failed", "timeout", None),)
        with mock.patch.object(transient_campaign, "SCENARIOS", mutant):
            report = transient_campaign.run_campaign()
        self.assertEqual(report["status"], "fail")
        self.assertIn("unexpected_terminal_result", report["cases"][0]["violations"])


if __name__ == "__main__":
    unittest.main()
