#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from g4_ota import validate_g4_evidence  # noqa: E402

FZ = Path(__file__).resolve().parent.parent


class TestG4Ota(unittest.TestCase):
    def test_sample_pass_when_ota(self) -> None:
        p = FZ / "release" / "g4_ota.dev-sample-pass.yaml"
        st, rep = validate_g4_evidence(p, {"ota": True})
        self.assertEqual(st, "pass", rep)

    def test_fail_on_explicit_fail(self) -> None:
        import tempfile

        text = """
version: t
items:
  - id: ota.enabled_in_product
    result: fail
    note: broken
  - id: ota.old_to_new_success
    result: pass
    note: x
  - id: ota.version_matches_artifact
    result: pass
    note: x
  - id: ota.failure_recovery_documented
    result: pass
    note: x
  - id: ota.usb_fallback_ok
    result: pass
    note: x
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "e.yaml"
            p.write_text(text, encoding="utf-8")
            st, rep = validate_g4_evidence(p, {"ota": True})
        self.assertEqual(st, "fail")
        self.assertTrue(rep.get("errors"))

    def test_missing_file(self) -> None:
        st, _ = validate_g4_evidence(Path("/no/such/g4.yaml"), {"ota": True})
        self.assertEqual(st, "unknown")


if __name__ == "__main__":
    unittest.main()
