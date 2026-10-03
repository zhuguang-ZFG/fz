#!/usr/bin/env python3
from __future__ import annotations

import unittest

from run_wokwi_smoke import classify_cloud_error, compute_blocking
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
        self.assertEqual(classify_cloud_error(1, "", "Client network socket disconnected before secure TLS connection was established"), "transport")
        self.assertEqual(classify_cloud_error(1, "", "Connection to transport closed unexpectedly: code 1006"), "transport")

    def test_exhausted_ci_quota_is_cloud_not_firmware(self) -> None:
        """实测文本（2026-09-27 活报告）：配额耗尽曾被当成固件启动失败判硬红。"""
        quota = "API Error: You have used up your Free plan monthly CI minute quota"
        self.assertEqual(classify_cloud_error(1, "", quota), "quota")
        self.assertEqual(classify_cloud_error(1, quota, ""), "quota")
        # 串口全空 = 固件从未执行 → 不阻断 host SIL
        self.assertFalse(compute_blocking("quota", ""))
        # 退出码 0 时同样文本不得改判（只认真实失败）
        self.assertIsNone(classify_cloud_error(0, "", quota))

    def test_firmware_evidence_still_blocks_despite_cloud_error(self) -> None:
        # 串口已有输出 → 即使归类为云错误也必须阻断
        self.assertTrue(compute_blocking("quota", "rst:0x1 (POWERON_RESET)\n"))
        self.assertTrue(compute_blocking("unauthorized", "Guru Meditation\n"))
        # 超时意味着模拟真的跑过，永远阻断
        self.assertTrue(compute_blocking("timeout", ""))
        self.assertTrue(compute_blocking(None, ""))


class TestQemuIpcGuruExemption(unittest.TestCase):
    """QEMU 首轮 POWERON 必现的一次性 Guru BREAK（ipc_task→esp_crosscore_int_send_yield，
    符号化见 2026-10-03 判别实验）属仿真多核 IPC 保真缺口，boot2 干净。
    豁免只在显式开启 + radio-off 夹具链内生效，且判据必须同时满足。"""

    RADIO_OFF_LOG = (
        "ets Jul 29 2019 12:21:46\n"
        "rst:0x1 (POWERON_RESET),boot:0x12 (SPI_FAST_FLASH_BOOT)\n"
        "entry 0x400806b8\n"
        "Guru Meditation Error: Core  1 panic'ed (Unhandled debug exception)\n"
        "Debug exception reason: BREAK instr \n"
        "Rebooting...\n"
        "rst:0xc (SW_CPU_RESET),boot:0x12 (SPI_FAST_FLASH_BOOT)\n"
        "[MSG:Grbl_ESP32 Ver 1.3a Date 20211103]\n"
        "[MSG:No spindle]\n"
        "Grbl 1.3a ['$' for help]\n"
        "ok\n"
    )

    def _exempt(self, log: str, markers=("Grbl",)) -> dict:
        return analyze_startup_log(
            log, list(markers), max_boots=2, qemu_ipc_guru_exemption=True
        )

    def test_single_first_boot_guru_passes_only_with_exemption(self) -> None:
        blocked = analyze_startup_log(self.RADIO_OFF_LOG, ["Grbl"], max_boots=2)
        self.assertEqual(blocked["status"], "fail", blocked)
        verdict = self._exempt(self.RADIO_OFF_LOG)
        self.assertEqual(verdict["status"], "pass", verdict)
        exemptions = verdict["artifact_exemptions"]
        self.assertEqual(len(exemptions), 1, verdict)
        self.assertEqual(exemptions[0]["kind"], "qemu_first_boot_ipc_guru")

    def test_guru_after_app_banner_is_not_exempted(self) -> None:
        log = self.RADIO_OFF_LOG.replace(
            "Guru Meditation Error: Core  1 panic'ed (Unhandled debug exception)\n"
            "Debug exception reason: BREAK instr \n"
            "Rebooting...\n",
            "",
        ) + "Guru Meditation Error: Core  1 panic'ed (Unhandled debug exception)\n"
        verdict = self._exempt(log)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertFalse(verdict["artifact_exemptions"])

    def test_two_guru_incidents_are_not_exempted(self) -> None:
        verdict = self._exempt(self.RADIO_OFF_LOG + self.RADIO_OFF_LOG)
        self.assertEqual(verdict["status"], "fail", verdict)

    def test_guru_without_ready_is_not_exempted(self) -> None:
        log = self.RADIO_OFF_LOG.replace("Grbl 1.3a ['$' for help]\n", "")
        verdict = self._exempt(log)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertFalse(verdict["artifact_exemptions"])

    def test_banner_without_prompt_is_not_exempted(self) -> None:
        """只有 [MSG:Grbl_ESP32 横幅、无 ['$' for help] 提示符 = 卡在 ready 前，
        弱标记 'Grbl' 也不得放行。"""
        log = self.RADIO_OFF_LOG.replace("Grbl 1.3a ['$' for help]\n", "")
        verdict = self._exempt(log, markers=["Grbl"])
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertFalse(verdict["artifact_exemptions"])

    def test_guru_without_reboot_is_not_exempted(self) -> None:
        """用户判据=首启 Guru 后 boot2 恢复；没有第二次启动（boot_count=1）
        说明固件没有从 artifact 中恢复，不得放行。"""
        log = self.RADIO_OFF_LOG.replace(
            "rst:0xc (SW_CPU_RESET),boot:0x12 (SPI_FAST_FLASH_BOOT)\n", ""
        )
        verdict = self._exempt(log)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertFalse(verdict["artifact_exemptions"])

    def test_guru_plus_other_fatal_is_not_exempted(self) -> None:
        log = self.RADIO_OFF_LOG + "Task watchdog got triggered\n"
        verdict = self._exempt(log)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertFalse(verdict["artifact_exemptions"])

    def test_bt_crash_loop_is_not_exempted(self) -> None:
        crash = (
            "rst:0x1 (POWERON_RESET)\n"
            "[MSG:Grbl_ESP32 Ver 1.3a]\n"
            "[MSG:No spindle]\n"
            'assertion "select_src_ret && set_div_ret" failed: bt.c line 1134\n'
            "abort() was called at PC 0x4015c6cb on core 1\n"
            "Rebooting...\n"
        )
        verdict = self._exempt(crash * 3)
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertTrue(verdict["restart_loop"])

    def test_guru_line_without_panic_word_is_not_exempted(self) -> None:
        log = self.RADIO_OFF_LOG.replace(
            "Guru Meditation Error: Core  1 panic'ed (Unhandled debug exception)",
            "Guru Meditation Error: Core  1 (Unhandled debug exception)",
        )
        verdict = self._exempt(log)
        self.assertEqual(verdict["status"], "fail", verdict)

    def test_exemption_defaults_off(self) -> None:
        verdict = analyze_startup_log(self.RADIO_OFF_LOG, ["Grbl"])
        self.assertEqual(verdict["status"], "fail", verdict)
        self.assertFalse(verdict["artifact_exemptions"])


if __name__ == "__main__":
    unittest.main()
