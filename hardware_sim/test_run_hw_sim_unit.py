#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for hardware_sim run isolation helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_hw_sim import atomic_write_json, build_repeat_command  # noqa: E402


class TestRunHwSimUnit(unittest.TestCase):
    def test_repeat_command_replaces_control_arguments(self) -> None:
        command = build_repeat_command(
            ["--start-sim", "--repeat", "20", "--run-id=old", "--only", "move_x"],
            "new-run",
        )
        self.assertEqual(command.count("--repeat"), 1)
        self.assertNotIn("20", command)
        self.assertNotIn("--run-id=old", command)
        self.assertEqual(command[-4:], ["--repeat", "1", "--run-id", "new-run"])
        self.assertIn("move_x", command)

    def test_atomic_json_write_replaces_complete_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "report.json"
            atomic_write_json(path, {"run_id": "first"})
            atomic_write_json(path, {"run_id": "second", "passed": True})
            data = json.loads(path.read_text(encoding="utf-8"))
            leftovers = list(path.parent.glob("*.tmp"))
        self.assertEqual(data, {"run_id": "second", "passed": True})
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
