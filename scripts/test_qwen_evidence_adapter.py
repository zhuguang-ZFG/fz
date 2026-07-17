#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("qwen_evidence_adapter", ROOT / "scripts" / "qwen_evidence_adapter.py")
assert SPEC and SPEC.loader
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


class TestQwenEvidenceAdapter(unittest.TestCase):
    def test_profiles_are_fixed_existing_test_targets(self) -> None:
        self.assertIn("standard", ADAPTER.PROFILES)
        self.assertIn("voice_contract", ADAPTER.PROFILES)
        self.assertIn("tests/test_firmware_hardware_gate.py", ADAPTER.PROFILES["standard"])
        self.assertIn("tests/test_device_app_voice_ws.py", ADAPTER.PROFILES["standard"])
        self.assertTrue(all(path.startswith("tests/") for path in ADAPTER.PROFILES["standard"]))

    def test_summary_parser_counts_pytest_outcomes(self) -> None:
        summary = ADAPTER.parse_summary("73 passed, 2 skipped, 1 failed in 1.2s")
        self.assertEqual(summary, {"passed": 73, "skipped": 2, "failed": 1})

    def test_unknown_profile_is_rejected_before_subprocess(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown QWEN profile"):
            ADAPTER.run_profile("shell", Path("D:/QWEN3.0"), "r1", 10)


if __name__ == "__main__":
    unittest.main()
