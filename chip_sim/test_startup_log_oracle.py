#!/usr/bin/env python3
from __future__ import annotations

import unittest

from run_wokwi_smoke import classify_cloud_error
from startup_log_oracle import analyze_startup_log


class TestStartupLogOracle(unittest.TestCase):
    def test_healthy_boot_reaches_ready_marker(self) -> None:
        report = analyze_startup_log("rst:0x1 (POWERON_RESET)\nGrbl 1.1 ['$' for help]\n", ["Grbl"])
        self.assertEqual(report["status"], "pass", report)

    def test_each_initialization_failure_is_rejected(self) -> None:
        bad_logs = {
            "guru_meditation": "Guru Meditation Error: Core 1 panic'ed",
            "watchdog": "Task watchdog got triggered",
            "brownout": "Brownout detector was triggered",
            "task_allocation": "Failed to create task protocolTask",
            "filesystem_mount": "SPIFFS mount failed",
            "radio_init": "Bluetooth init failed",
            "i2s_init": "I2S driver install failed",
            "restart_loop": "rst:0x1\nrst:0x3\nrst:0x3\nGrbl 1.1",
        }
        for expected, log in bad_logs.items():
            with self.subTest(expected=expected):
                report = analyze_startup_log(log + "\nGrbl 1.1\n", ["Grbl"])
                self.assertEqual(report["status"], "fail")
                self.assertIn(expected, {event["kind"] for event in report["fatal_events"]})

    def test_missing_ready_marker_is_rejected(self) -> None:
        report = analyze_startup_log("rst:0x1\nbooting...\n", ["Grbl"])
        self.assertEqual(report["status"], "fail")
        self.assertIn("ready_timeout", {event["kind"] for event in report["fatal_events"]})

    def test_cloud_errors_are_not_misclassified_as_firmware_startup(self) -> None:
        self.assertEqual(classify_cloud_error(1, "", "API Error: Unauthorized"), "unauthorized")
        self.assertEqual(classify_cloud_error(42, "", ""), "timeout")
        self.assertIsNone(classify_cloud_error(1, "simulation failed", ""))


if __name__ == "__main__":
    unittest.main()
