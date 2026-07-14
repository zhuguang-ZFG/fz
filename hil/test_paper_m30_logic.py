#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline tests for paper_m30 helpers (no serial)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_m30_serial import PAPER_DONE, PAGE_END, steps_to_g3_yaml_items  # noqa: E402


class TestPaperPatterns(unittest.TestCase):
    def test_paper_done_pattern(self) -> None:
        self.assertTrue(PAPER_DONE.search("[PaperM30] Auto paper change completed"))

    def test_page_end(self) -> None:
        self.assertTrue(PAGE_END.search("[MSG:PAGE_END_IMMINENT]"))

    def test_patches(self) -> None:
        steps = [
            {
                "id": "paper.1.1",
                "ok": True,
                "result": "pass",
                "note": "x",
                "snippet": "ok",
            }
        ]
        p = steps_to_g3_yaml_items(steps)
        self.assertEqual(p[0]["id"], "paper.1.1")
        self.assertEqual(p[0]["result"], "pass")


if __name__ == "__main__":
    unittest.main()
