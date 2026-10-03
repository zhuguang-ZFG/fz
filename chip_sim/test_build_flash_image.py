#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_flash_image import SIZE_MAP, pure_merge, find_build_artifacts, find_nvs_partition  # noqa: E402
from build_flash_image import main as build_main  # noqa: E402
from radio_off_fixture import FIXTURE_PATH, RADIO_OFF_NVS_SHA256  # noqa: E402

class TestRadioOffFixtureIntegrity(unittest.TestCase):
    """钉死的 radio-off 夹具：内容=仅 Grbl_ESP32/Radio/Mode=0（ESP_RADIO_OFF），
    任何替换都必须连钉死 SHA 一起改，测试即审查点。"""

    def test_shipped_fixture_matches_pinned_sha256(self) -> None:
        import hashlib

        digest = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, RADIO_OFF_NVS_SHA256)
        self.assertEqual(FIXTURE_PATH.stat().st_size, 0x5000)


class TestPureMerge(unittest.TestCase):
    def test_missing_requested_environment_never_uses_another_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other = root / ".pio/build/other"
            other.mkdir(parents=True)
            (other / "firmware.bin").write_bytes(b"wrong-board")
            self.assertIsNone(find_build_artifacts(root, "release")["firmware"])

    def test_merge_layout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            b = t / "b.bin"
            p = t / "p.bin"
            a = t / "a.bin"
            b.write_bytes(b"\x01\x02")
            p.write_bytes(b"\x03")
            a.write_bytes(b"\x04\x05\x06")
            out = t / "flash.bin"
            pure_merge(
                [(0x1000, b), (0x8000, p), (0x10000, a)],
                out,
                SIZE_MAP["4MB"],
            )
            data = out.read_bytes()
            self.assertEqual(len(data), SIZE_MAP["4MB"])
            self.assertEqual(data[0x1000:0x1002], b"\x01\x02")
            self.assertEqual(data[0x8000], 0x03)
            self.assertEqual(data[0x10000:0x10003], b"\x04\x05\x06")
            self.assertEqual(data[0], 0xFF)


def _partitions_with_nvs(nvs_off: int = 0x9000, nvs_size: int = 0x5000) -> bytes:
    """最小合法分区表：nvs + app0，尾随 0xFF 结束。"""
    def _entry(ptype: int, subtype: int, off: int, size: int, name: bytes) -> bytes:
        return (
            b"\xaa\x50"
            + bytes([ptype, subtype])
            + off.to_bytes(4, "little")
            + size.to_bytes(4, "little")
            + name.ljust(16, b"\x00")
            + b"\x00" * 4
        )

    table = _entry(0x01, 0x02, nvs_off, nvs_size, b"nvs") + _entry(
        0x00, 0x10, 0x10000, 0x1E0000, b"app0"
    )
    return table + b"\xff" * (0x1000 - len(table))


class TestFindNvsPartition(unittest.TestCase):
    def test_parses_nvs_entry(self) -> None:
        self.assertEqual(find_nvs_partition(_partitions_with_nvs()), (0x9000, 0x5000))

    def test_missing_nvs_returns_none(self) -> None:
        table = _partitions_with_nvs()
        # 把 nvs 条目的 subtype 改掉（0x02 → 0x99）
        broken = table[:3] + b"\x99" + table[4:]
        self.assertIsNone(find_nvs_partition(broken))

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(find_nvs_partition(b"\x00" * 64))


class TestNvsFixtureInjection(unittest.TestCase):
    def _write_inputs(self, root: Path) -> None:
        (root / "boot.bin").write_bytes(b"\xAA" * 0x100)
        (root / "part.bin").write_bytes(_partitions_with_nvs())
        (root / "fw.bin").write_bytes(b"\xBB" * 0x200)
        (root / "nvs.bin").write_bytes(b"\x42" * 0x5000)

    def _args(self, root: Path, *extra: str) -> list:
        argv = [
            "--grbl-root", str(root / "nonexistent"),
            "--bootloader", str(root / "boot.bin"),
            "--partitions", str(root / "part.bin"),
            "--firmware", str(root / "fw.bin"),
            "--out", str(root / "out.bin"),
        ]
        return argv + list(extra)

    def test_fixture_injected_at_nvs_offset_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_inputs(root)
            rc = build_main(self._args(root, "--nvs-fixture", str(root / "nvs.bin")))
            self.assertEqual(rc, 0)
            image = (root / "out.bin").read_bytes()
            self.assertEqual(image[0x9000:0x9000 + 0x5000], b"\x42" * 0x5000)
            import json as _json

            sidecar = _json.loads((root / "out.json").read_text(encoding="utf-8"))
            nvs = sidecar["nvs"]
            self.assertFalse(nvs["radio_off"])
            self.assertEqual(nvs["offset"], "0x9000")
            self.assertEqual(nvs["bytes"], 0x5000)
            self.assertEqual(len(nvs["sha256"]), 64)

    def test_pinned_fixture_marks_radio_off(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_inputs(root)
            rc = build_main(self._args(root, "--nvs-fixture", str(FIXTURE_PATH)))
            self.assertEqual(rc, 0)
            import json as _json

            sidecar = _json.loads((root / "out.json").read_text(encoding="utf-8"))
            nvs = sidecar["nvs"]
            self.assertTrue(nvs["radio_off"])
            self.assertEqual(nvs["sha256"], RADIO_OFF_NVS_SHA256)

    def test_no_fixture_leaves_region_erased_and_sidecar_clean(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_inputs(root)
            rc = build_main(self._args(root))
            self.assertEqual(rc, 0)
            image = (root / "out.bin").read_bytes()
            self.assertEqual(image[0x9000:0x9000 + 0x5000], b"\xff" * 0x5000)
            import json as _json

            sidecar = _json.loads((root / "out.json").read_text(encoding="utf-8"))
            self.assertNotIn("nvs", sidecar)

    def test_oversize_fixture_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_inputs(root)
            (root / "nvs.bin").write_bytes(b"\x42" * (0x5000 + 1))
            rc = build_main(self._args(root, "--nvs-fixture", str(root / "nvs.bin")))
            self.assertEqual(rc, 2)
            self.assertFalse((root / "out.bin").exists())

    def test_missing_fixture_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_inputs(root)
            rc = build_main(
                self._args(root, "--nvs-fixture", str(root / "absent.bin"))
            )
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
