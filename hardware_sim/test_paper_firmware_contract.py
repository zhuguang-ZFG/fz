#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from run_paper_firmware_contract import load_contract, parse_numeric_defines, validate_contract


class TestPaperFirmwareContract(unittest.TestCase):
    def test_parser_accepts_integer_suffixes_and_ignores_expressions(self) -> None:
        values = parse_numeric_defines("#define A 15u\n#define B 0x20UL\n#define C (A + B)\n")
        self.assertEqual(values, {"A": 15, "B": 32})

    def test_repository_contract_matches_product_and_plant(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        contract = load_contract(Path(__file__).with_name("paper_firmware_contract.json"))
        report = validate_contract(contract, grbl_root)
        self.assertEqual(report["status"], "pass", report["violations"])

    def test_detects_firmware_and_plant_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Grbl_Esp32" / "src" / "PaperSystem.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("#define PAPER_SENSOR_TIMEOUT_MS 12000u\n", encoding="utf-8")
            contract = {
                "version": 1,
                "firmware_constants": {"Grbl_Esp32/src/PaperSystem.cpp": {"PAPER_SENSOR_TIMEOUT_MS": 15000}},
                "plant_abstractions": {"timeout_ms": {"expected": 2400, "kind": "scaled_from_firmware", "firmware_constant": "PAPER_SENSOR_TIMEOUT_MS", "scale_numerator": 1, "scale_denominator": 5}},
            }
            report = validate_contract(contract, root)
            kinds = {item["kind"] for item in report["violations"]}
            self.assertIn("firmware_drift", kinds)
            self.assertIn("plant_drift", kinds)

    def test_rejects_invalid_contract_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"version": 2}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                load_contract(path)


if __name__ == "__main__":
    unittest.main()
