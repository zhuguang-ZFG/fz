#!/usr/bin/env python3
from __future__ import annotations

import unittest

from run_protocol_decision_diff import classify_pair, run_diff


class TestProtocolDecisionDiff(unittest.TestCase):
    def test_rejected_reference_is_not_called_product_bug(self) -> None:
        product = {"motion_g0_g3": True}
        self.assertEqual(classify_pair(product, "error", "22"), "reference_rejected")

    def test_product_motion_is_explicitly_labeled(self) -> None:
        product = {"motion_g0_g3": True}
        self.assertEqual(classify_pair(product, "ok", None), "product_motion_reference_ok")

    def test_non_motion_reference_acceptance_is_explicit(self) -> None:
        product = {"motion_g0_g3": False}
        self.assertEqual(classify_pair(product, "ok", None), "reference_ok_product_non_motion")

    def test_rejects_non_positive_timeout_before_starting_sim(self) -> None:
        with self.assertRaisesRegex(ValueError, "timeout must be positive"):
            run_diff([], __import__("pathlib").Path("."), timeout=0)


if __name__ == "__main__":
    unittest.main()
