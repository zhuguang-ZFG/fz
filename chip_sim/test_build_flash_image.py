#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_flash_image import SIZE_MAP, pure_merge  # noqa: E402


class TestPureMerge(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
