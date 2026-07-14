#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_serial_log import archive_text, write_session_index


class TestArchiveSerialLog(unittest.TestCase):
    def test_archive_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            meta = archive_text(
                "hello\nok\n",
                kind="unit_test",
                port="COM99",
                results_dir=root,
            )
            self.assertTrue(Path(meta["log_path"]).is_file())
            self.assertGreater(meta["bytes"], 0)
            write_session_index(
                [meta],
                out_md=root / "idx.md",
                out_json=root / "idx.json",
            )
            self.assertTrue((root / "idx.md").is_file())
            self.assertIn("unit_test", (root / "idx.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
