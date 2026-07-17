#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from run_firmware_contract import compare, load_contract, validate_contract


class TestXiaozhiFirmwareContract(unittest.TestCase):
    def test_repository_contract_matches_product_and_model(self) -> None:
        qwen_root = Path(os.environ.get("QWEN_ROOT", "D:/QWEN3.0"))
        if not qwen_root.is_dir():
            self.skipTest("QWEN_ROOT unavailable")
        report = validate_contract(load_contract(Path(__file__).with_name("firmware_contract.json")), qwen_root)
        self.assertEqual(report["status"], "pass", report["violations"])
        self.assertEqual(report["observed_model"]["server_hello_type"], "hello_ack")
        self.assertIn("run_path", report["observed_model"]["capabilities"])

    def test_compare_detects_scalar_and_set_drift(self) -> None:
        violations = []
        compare("root", {"protocol": "v1", "types": ["a", "b"]}, {"protocol": "v2", "types": ["a"]}, violations)
        self.assertEqual({item["field"] for item in violations}, {"root.protocol", "root.types"})

    def test_source_audio_mutation_must_fail(self) -> None:
        qwen_root = Path(os.environ.get("QWEN_ROOT", "D:/QWEN3.0"))
        source_root = qwen_root / "esp32S_XYZ/firmware/u8-xiaozhi"
        if not source_root.is_dir():
            self.skipTest("QWEN Xiaozhi firmware unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = root / "esp32S_XYZ/firmware/u8-xiaozhi/main"
            (firmware / "protocols").mkdir(parents=True)
            websocket = (source_root / "main/protocols/websocket_protocol.cc").read_text(encoding="utf-8", errors="replace")
            websocket = websocket.replace('AddStringToObject(audio_params, "format", "pcm")', 'AddStringToObject(audio_params, "format", "opus")')
            (firmware / "protocols/websocket_protocol.cc").write_text(websocket, encoding="utf-8")
            (firmware / "application.cc").write_text((source_root / "main/application.cc").read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            report = validate_contract(load_contract(Path(__file__).with_name("firmware_contract.json")), root)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(item["field"] == "firmware.audio.format" for item in report["violations"]))

    def test_rejects_bad_contract_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"version": 2}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version"):
                load_contract(path)

    def test_rejects_incomplete_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"version": 1, "firmware_root": "firmware", "expected": {"protocol": "v1"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected"):
                load_contract(path)

    def test_firmware_path_cannot_escape_qwen_root(self) -> None:
        contract = load_contract(Path(__file__).with_name("firmware_contract.json"))
        contract["firmware_root"] = "../outside"
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "escapes"):
            validate_contract(contract, Path(directory))


if __name__ == "__main__":
    unittest.main()
