#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

FZ = Path(__file__).resolve().parent.parent


class TestAgentGate(unittest.TestCase):
    def test_contract(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "agent_gate.py"), "--print-contract"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("agent_gate", r.stdout.lower())

    def test_quick_profile(self) -> None:
        r = subprocess.run(
            [
                sys.executable,
                str(FZ / "scripts" / "agent_gate.py"),
                "--profile",
                "quick",
            ],
            cwd=str(FZ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=420,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout[-2000:] + r.stderr[-1000:])
        rep = FZ / "results" / "agent_gate_last.json"
        self.assertTrue(rep.is_file())
        data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(data["suite"], "agent_gate")
        self.assertEqual(data["overall_status"], "pass")
        self.assertIn("agent_hints", data)
        hw = [x for x in data["layers"] if x["id"] == "hardware"][0]
        self.assertEqual(hw["status"], "skip")

class TestAgentGateQemuLayer(unittest.TestCase):
    """镜像来源和失败传播使用真实门禁层，模拟外部进程结果。"""

    def test_missing_runtime_skips(self):
        from scripts.agent_gate import run_qemu_layer
        self.assertEqual(run_qemu_layer(None, "dio", Path("qemu" )).status, "skip")
        self.assertEqual(run_qemu_layer(Path("grbl"), "dio", None).status, "skip")

    def test_merge_failure_blocks_even_when_old_flash_exists(self):
        import scripts.agent_gate as ag
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            (results / "qemu").mkdir()
            (results / "qemu/flash_image_4mb.bin").write_bytes(b"old-image")
            with mock.patch.object(ag, "RESULTS", results), mock.patch.object(ag, "_run", return_value=(1, 0.1)) as run:
                layer = ag.run_qemu_layer(results, "dio", Path("qemu"))
            self.assertEqual(layer.status, "fail")
            self.assertTrue(layer.blocking)
            self.assertEqual(run.call_count, 1)

    def test_release_selected_and_startup_failure_propagated(self):
        import scripts.agent_gate as ag
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".pio/build/qemu").mkdir(parents=True)
            (root / ".pio/build/qemu/firmware.bin").write_bytes(b"old-qemu-app")
            def execute(command, **kwargs):
                if "--pio-env" in command:
                    self.assertEqual(command[command.index("--pio-env") + 1], "release")
                    image = Path(command[command.index("--out") + 1])
                    image.parent.mkdir(parents=True)
                    image.write_bytes(b"current-release")
                    return 0, 0.1
                self.assertEqual(Path(command[command.index("--flash") + 1]).read_bytes(), b"current-release")
                return 2, 0.2
            with mock.patch.object(ag, "RESULTS", root), mock.patch.object(ag, "_run", side_effect=execute) as run:
                layer = ag.run_qemu_layer(root, "dio", Path("qemu"))
            self.assertEqual(run.call_count, 2)
            self.assertEqual((layer.status, layer.exit_code), ("fail", 2))

    def test_success_without_merged_output_is_failure(self):
        import scripts.agent_gate as ag
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(ag, "RESULTS", Path(directory)), mock.patch.object(ag, "_run", return_value=(0, 0.1)) as run:
                layer = ag.run_qemu_layer(Path(directory), "dio", Path("qemu"))
            self.assertEqual(layer.status, "fail")
            self.assertEqual(run.call_count, 1)


class TestChipEvidenceVerdict(unittest.TestCase):
    """陈旧镜像假绿通道（必修#1）：镜像旧于源码时 chip 启动层必须判负。"""

    def test_stale_image_fails_and_blocks_even_on_zero_exit(self):
        from scripts.agent_gate import chip_evidence_verdict
        for suite in ("qemu_startup", "wokwi_startup"):
            with self.subTest(suite=suite):
                status, blocking, detail = chip_evidence_verdict(
                    suite, 0, {"firmware_stale_vs_source": True}
                )
                self.assertEqual(status, "fail")
                self.assertTrue(blocking)
                self.assertIn("源码", detail or "")

    def test_fresh_image_with_zero_exit_passes(self):
        from scripts.agent_gate import chip_evidence_verdict
        status, blocking, detail = chip_evidence_verdict(
            "qemu_startup", 0, {"firmware_stale_vs_source": False}
        )
        self.assertEqual((status, blocking, detail), ("pass", None, None))
        # 无法判定（无 GRBL_ROOT 等）不得凭空判负
        status, _, _ = chip_evidence_verdict("qemu_startup", 0, {"firmware_stale_vs_source": None})
        self.assertEqual(status, "pass")

    def test_missing_round_report_is_not_a_pass(self):
        from scripts.agent_gate import chip_evidence_verdict
        status, blocking, detail = chip_evidence_verdict("wokwi_startup", 0, None)
        self.assertEqual(status, "fail")
        self.assertTrue(blocking)
        self.assertIn("新鲜度", detail or "")

    def test_nonzero_exit_leaves_blocking_to_caller(self):
        from scripts.agent_gate import chip_evidence_verdict
        status, blocking, detail = chip_evidence_verdict("wokwi_startup", 1, {"blocking": False})
        self.assertEqual((status, blocking, detail), ("fail", None, None))

    def test_stale_report_file_is_not_this_round(self):
        import os
        import scripts.agent_gate as ag
        with tempfile.TemporaryDirectory() as directory:
            rep = Path(directory) / "r.json"
            rep.write_text(json.dumps({"firmware_stale_vs_source": False}), encoding="utf-8")
            unchanged = ag._report_mtime(rep)
            # 运行前后 mtime 没变 = 本轮没重写报告 → 无证据
            self.assertIsNone(ag._fresh_chip_report(rep, unchanged))
            # 缺文件 → 无证据
            self.assertIsNone(ag._fresh_chip_report(Path(directory) / "nope.json", None))
            # 本轮重写过 → 采信
            old = (unchanged or time.time()) - 600
            os.utime(rep, (old, old))
            self.assertIsNotNone(ag._fresh_chip_report(rep, unchanged))

    def test_qemu_layer_fails_on_stale_image_report(self):
        import scripts.agent_gate as ag
        for stale, expected in ((True, "fail"), (False, "pass"), (None, "pass")):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)

                def execute(command, **kwargs):
                    if "--pio-env" in command:
                        image = Path(command[command.index("--out") + 1])
                        image.parent.mkdir(parents=True, exist_ok=True)
                        image.write_bytes(b"current-release")
                        return 0, 0.1
                    rep = root / "qemu" / "qemu_smoke_report.json"
                    rep.parent.mkdir(parents=True, exist_ok=True)
                    rep.write_text(
                        json.dumps({"firmware_stale_vs_source": stale}), encoding="utf-8"
                    )
                    return 0, 0.2

                with mock.patch.object(ag, "RESULTS", root), mock.patch.object(
                    ag, "_run", side_effect=execute
                ):
                    layer = ag.run_qemu_layer(root, "dio", Path("qemu"))
                self.assertEqual(layer.status, expected, msg=layer.detail)

    def test_qemu_layer_fails_when_runner_writes_no_report(self):
        import scripts.agent_gate as ag
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def execute(command, **kwargs):
                if "--pio-env" in command:
                    image = Path(command[command.index("--out") + 1])
                    image.parent.mkdir(parents=True, exist_ok=True)
                    image.write_bytes(b"current-release")
                return 0, 0.1

            with mock.patch.object(ag, "RESULTS", root), mock.patch.object(
                ag, "_run", side_effect=execute
            ):
                layer = ag.run_qemu_layer(root, "dio", Path("qemu"))
            self.assertEqual(layer.status, "fail")
            self.assertIn("新鲜度", layer.detail)


class TestAgentGateFailureHints(unittest.TestCase):
    def test_every_failed_layer_gets_a_failure_hint(self):
        import scripts.agent_gate as ag
        for name in ("qemu_startup", "wokwi_startup", "future_new_layer"):
            with self.subTest(name=name):
                hints = ag.agent_hints_for_failures([ag.Layer(id=name, name=name, status="fail")])
                self.assertNotIn("No hard failures.", hints)
                self.assertTrue(any(name in hint and "failed" in hint for hint in hints))


if __name__ == "__main__":
    unittest.main()
