#!/usr/bin/env python3
from __future__ import annotations

import unittest

from paper_plant import FaultProfile, PaperPlantConfig, simulate
from run_paper_plant_interactions import configurations, pairwise_coverage, property_violations, run_interactions


class TestPaperPlantInteractions(unittest.TestCase):
    def test_campaign_exhausts_bounded_space(self) -> None:
        report = run_interactions()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["configuration_count"], 48)
        self.assertEqual(report["interaction_coverage"]["covered"], 44)
        self.assertEqual(report["interaction_coverage"]["ratio"], 1.0)
        self.assertIsNone(report["minimal_failure"])

    def test_pairwise_coverage_detects_missing_interactions(self) -> None:
        coverage = pairwise_coverage(list(configurations())[:1])
        self.assertLess(coverage["ratio"], 1.0)
        self.assertTrue(coverage["missing"])

    def test_properties_reject_unsafe_completion(self) -> None:
        config = {"paper": "missing", "speed": "normal", "drive": "normal", "sensor": "normal"}
        result = simulate(PaperPlantConfig(), FaultProfile(name="missing", paper_present=False))
        forged = dict(result, outcome="completed", reason="paper_positioned")
        violations = property_violations(config, forged, forged)
        self.assertIn("unsafe_or_missing_completion", violations)


if __name__ == "__main__":
    unittest.main()
