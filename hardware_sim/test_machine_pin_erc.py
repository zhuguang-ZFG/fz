#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from run_machine_pin_erc import load_contract, parse_defines, resolve, validate_contract
from run_machine_pin_mutation_campaign import run_campaign


class TestMachinePinErc(unittest.TestCase):
    def test_checker_kills_every_declared_preflash_mutation(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        report = run_campaign(grbl_root)
        self.assertEqual(report["status"], "pass", report["failures"])
        self.assertTrue(report["baseline_passed"])
        self.assertEqual(report["mutation_score"], {"killed": 6, "total": 6})

    def test_parser_resolves_gpio_i2so_and_aliases(self) -> None:
        defines = parse_defines("#define A GPIO_NUM_25\n#define B I2SO(3)\n#define C A\n")
        self.assertEqual(resolve("A", defines), "GPIO25")
        self.assertEqual(resolve("B", defines), "I2SO3")
        self.assertEqual(resolve("C", defines), "GPIO25")

    def test_repository_machine_passes_with_reviewed_warnings(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        report = validate_contract(load_contract(Path(__file__).with_name("machine_pin_contract.json")), grbl_root)
        self.assertEqual(report["status"], "pass", report["errors"])
        self.assertEqual({item["role"] for item in report["warnings"]}, {"X_STEP_PIN", "X_DIRECTION_PIN", "Y_DIRECTION_PIN"})
        self.assertEqual(report["coverage"], {"resolvable_pin_macros": 28, "contracted_pin_macros": 28, "uncontracted_pin_macros": 0, "percent": 100.0})
        self.assertEqual(report["next_actions"], [])

    def test_input_only_output_mutation_must_fail(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        source = grbl_root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
        if not source.is_file():
            self.skipTest("product machine unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
            target.parent.mkdir(parents=True)
            target.write_text(source.read_text(encoding="utf-8", errors="replace").replace("#define X_STEP_PIN              GPIO_NUM_2", "#define X_STEP_PIN              GPIO_NUM_34"), encoding="utf-8")
            report = validate_contract(load_contract(Path(__file__).with_name("machine_pin_contract.json")), root)
        kinds = {item["kind"] for item in report["errors"]}
        self.assertEqual(report["status"], "fail")
        self.assertIn("input_only_output", kinds)
        self.assertIn("pin_drift", kinds)

    def test_i2so_out_of_range_must_fail(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        source = grbl_root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
        if not source.is_file():
            self.skipTest("product machine unavailable")
        contract = load_contract(Path(__file__).with_name("machine_pin_contract.json"))
        contract["i2so_width"] = 7
        report = validate_contract(contract, grbl_root)
        findings = [item for item in report["errors"] if item["kind"] == "i2so_out_of_range"]
        self.assertEqual(findings, [{"kind": "i2so_out_of_range", "role": "FEEDER_MOTOR_STEP_PIN", "endpoint": "I2SO7", "width": 7}])

    def test_physical_pin_collision_must_fail(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        source = grbl_root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
        if not source.is_file():
            self.skipTest("product machine unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
            target.parent.mkdir(parents=True)
            target.write_text(source.read_text(encoding="utf-8", errors="replace").replace("#define Y_STEP_PIN              GPIO_NUM_13", "#define Y_STEP_PIN              GPIO_NUM_14"), encoding="utf-8")
            report = validate_contract(load_contract(Path(__file__).with_name("machine_pin_contract.json")), root)
        collisions = [item for item in report["errors"] if item["kind"] == "pin_collision"]
        self.assertEqual(collisions, [{"kind": "pin_collision", "endpoint": "GPIO14", "roles": ["Y_STEP_PIN", "Z_STEP_PIN"]}])

    def test_unreviewed_strapping_output_must_fail(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        contract = load_contract(Path(__file__).with_name("machine_pin_contract.json"))
        del contract["strapping_output_waivers"]["X_STEP_PIN"]
        report = validate_contract(contract, grbl_root)
        findings = [item for item in report["errors"] if item["kind"] == "strapping_output"]
        self.assertEqual(findings[0]["role"], "X_STEP_PIN")
        self.assertFalse(findings[0]["reviewed"])

    def test_new_pin_macro_must_be_contracted(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        source = grbl_root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
        if not source.is_file():
            self.skipTest("product machine unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
            target.parent.mkdir(parents=True)
            target.write_text(source.read_text(encoding="utf-8", errors="replace") + "\n#define NEW_SAFETY_OUTPUT_PIN GPIO_NUM_22\n", encoding="utf-8")
            report = validate_contract(load_contract(Path(__file__).with_name("machine_pin_contract.json")), root)
        findings = [item for item in report["errors"] if item["kind"] == "uncontracted_pin_macro"]
        self.assertEqual(findings, [{"kind": "uncontracted_pin_macro", "macros": {"NEW_SAFETY_OUTPUT_PIN": "GPIO22"}}])
        self.assertEqual(report["coverage"]["uncontracted_pin_macros"], 1)
        self.assertIn("Classify the new pin macro", report["next_actions"][0])

    def test_stale_endpoint_bound_waiver_must_fail(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        contract = load_contract(Path(__file__).with_name("machine_pin_contract.json"))
        contract["strapping_output_waivers"]["X_STEP_PIN"]["endpoint"] = "GPIO5"
        report = validate_contract(contract, grbl_root)
        kinds = {item["kind"] for item in report["errors"]}
        self.assertIn("strapping_output", kinds)
        self.assertIn("stale_strapping_waiver", kinds)

    def test_contract_rejects_unjustified_waiver(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        contract = load_contract(Path(__file__).with_name("machine_pin_contract.json"))
        contract["strapping_output_waivers"]["X_STEP_PIN"]["reason"] = ""
        report = validate_contract(contract, grbl_root)
        self.assertIn("contract_schema", {item["kind"] for item in report["errors"]})

    def test_invalid_and_flash_reserved_gpio_must_fail(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        source = grbl_root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
        if not source.is_file():
            self.skipTest("product machine unavailable")
        for replacement, expected_kind in (("GPIO_NUM_40", "invalid_gpio"), ("GPIO_NUM_6", "flash_reserved_gpio")):
            with self.subTest(endpoint=replacement), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / "Grbl_Esp32/src/Machines/custom_3axis_hr4988.h"
                target.parent.mkdir(parents=True)
                target.write_text(source.read_text(encoding="utf-8", errors="replace").replace("#define X_STEP_PIN              GPIO_NUM_2", f"#define X_STEP_PIN              {replacement}"), encoding="utf-8")
                report = validate_contract(load_contract(Path(__file__).with_name("machine_pin_contract.json")), root)
            self.assertIn(expected_kind, {item["kind"] for item in report["errors"]})

    def test_malformed_contract_values_report_errors_without_crashing(self) -> None:
        grbl_root = Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32"))
        if not grbl_root.is_dir():
            self.skipTest("GRBL_ROOT unavailable")
        contract = load_contract(Path(__file__).with_name("machine_pin_contract.json"))
        contract["roles"]["X_STEP_PIN"] = "GPIO2"
        contract["aliases"] = []
        contract["strapping_output_waivers"] = []
        contract["i2so_width"] = "8"
        report = validate_contract(contract, grbl_root)
        self.assertEqual(report["status"], "fail")
        self.assertIn("contract_schema", {item["kind"] for item in report["errors"]})

    def test_machine_path_cannot_escape_grbl_root(self) -> None:
        contract = load_contract(Path(__file__).with_name("machine_pin_contract.json"))
        contract["machine"] = "../outside.h"
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "escapes"):
            validate_contract(contract, Path(directory))

    def test_rejects_bad_contract_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"version": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                load_contract(path)


if __name__ == "__main__":
    unittest.main()
