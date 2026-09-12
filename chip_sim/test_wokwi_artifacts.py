#!/usr/bin/env python3
"""模拟输入必须保留真实启动程序/分区，并拒绝旧合并产物。"""
from pathlib import Path
import json
import tempfile
import unittest

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
