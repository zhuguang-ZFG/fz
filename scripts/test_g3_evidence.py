#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for g3_evidence validation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from g3_evidence import validate_g3_evidence  # noqa: E402

FZ = Path(__file__).resolve().parent.parent


class TestG3Evidence(unittest.TestCase):
    def test_dev_sample_pass_g3a_only(self) -> None:
        p = FZ / "release" / "g3_evidence.dev-sample-pass.yaml"
        st, rep = validate_g3_evidence(p, {"paper_path": False, "bluetooth": False})
        self.assertEqual(st, "pass", rep)

    def test_sample_fails_when_paper_required(self) -> None:
        p = FZ / "release" / "g3_evidence.dev-sample-pass.yaml"
        st, rep = validate_g3_evidence(p, {"paper_path": True})
        self.assertEqual(st, "fail")
        self.assertTrue(any("paper" in e for e in rep.get("errors", [])))

    def test_missing_file(self) -> None:
        st, rep = validate_g3_evidence(Path("/no/such/file.yaml"), {})
        self.assertEqual(st, "unknown")


if __name__ == "__main__":
    unittest.main()
