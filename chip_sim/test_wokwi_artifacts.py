#!/usr/bin/env python3
"""模拟输入必须保留真实启动程序/分区，并拒绝旧合并产物。"""
from pathlib import Path
import json
import tempfile
import unittest
from unittest import mock
import subprocess
import run_wokwi_smoke as wokwi

from run_wokwi_smoke import write_wokwi_toml


class TestWokwiArtifacts(unittest.TestCase):
    def make_artifacts(self, root):
        app = root / "firmware.bin"
        app.write_bytes(b"\xe9current-application")
        table = b"\xaa\x50current-partitions"
        (root / "partitions.bin").write_bytes(table)
        image = bytearray(b"\xff" * 0x11000)
        image[0x1000] = 0xe9
        image[0x8000:0x8000 + len(table)] = table
        image[0x10000:0x10000 + app.stat().st_size] = app.read_bytes()
        full = root / "firmware_full_0x0.bin"
        full.write_bytes(image)
        return app, full

    def test_full_observation_rejects_late_panic_early_exit_and_stale_uart(self):
        ready = "Grbl 1.3a ['$' for help]\n"
        cases = [
            (43, ready, 0),
            (43, "[MSG:Grbl_ESP32 Ver 1.3a]\n", 1),
            (43, ready + "Guru Meditation Error: Core 0 panic'ed\n", 1),
            (0, ready, 1),
            (1, None, 1),
        ]
        for code, uart, expected in cases:
            with self.subTest(code=code, uart=uart), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                build = root / ".pio/build/release"
                build.mkdir(parents=True)
                app, full = self.make_artifacts(build)
                output = root / "output"
                output.mkdir()
                (output / "serial.log").write_text(ready)
                def simulate(command, **kwargs):
                    self.assertNotIn("--expect-text", command)
                    self.assertIn("--timeout-exit-code", command)
                    self.assertEqual((output / "serial.log").read_text(), "")
                    if uart is not None:
                        (output / "serial.log").write_text(uart)
                    return subprocess.CompletedProcess(command, code, "", "")
                with mock.patch.object(wokwi, "RESULTS", output), mock.patch.object(wokwi, "find_wokwi_cli", return_value="wokwi-cli"), mock.patch.dict(wokwi.os.environ, {"WOKWI_CLI_TOKEN": "test"}), mock.patch.object(wokwi.subprocess, "run", side_effect=simulate):
                    actual = wokwi.main(["--grbl-root", str(root), "--flash", str(full), "--require"])
                self.assertEqual(actual, expected)

    def test_resolver_never_picks_other_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            other = root / ".pio/build/old"
            other.mkdir(parents=True)
            (other / "firmware.bin").write_bytes(b"wrong-image")
            self.assertEqual(wokwi.resolve_firmware(root), (None, None))

    def test_explicit_merged_image_still_checks_current_application(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app, full = self.make_artifacts(root)
            external = root / "merged-by-fz.bin"
            full.rename(external)
            write_wokwi_toml(app, None, root / "out", external)
            app.write_bytes(b"new-application")
            with self.assertRaisesRegex(ValueError, "does not match"):
                write_wokwi_toml(app, None, root / "out", external)

    def test_manifest_loads_complete_flash_at_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app, full = self.make_artifacts(root)
            config = write_wokwi_toml(app, None, root / "out")
            self.assertIn("firmware = 'flasher_args.json'", config.read_text(encoding="utf-8"))
            manifest = json.loads((config.parent / "flasher_args.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["flash_files"], {"0x0": "firmware.bin"})
            self.assertEqual((config.parent / "firmware.bin").read_bytes(), full.read_bytes())

    def test_stale_application_or_partitions_are_rejected(self):
        for name in ("firmware.bin", "partitions.bin"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                app, _ = self.make_artifacts(root)
                (root / name).write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "does not match"):
                    write_wokwi_toml(app, None, root / "out")

    def test_missing_full_image_does_not_fall_back_to_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app, full = self.make_artifacts(root)
            full.unlink()
            with self.assertRaisesRegex(ValueError, "complete PlatformIO"):
                write_wokwi_toml(app, None, root / "out")


if __name__ == "__main__":
    unittest.main()
