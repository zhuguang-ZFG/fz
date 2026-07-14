#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_block_oracle():
    path = Path(__file__).resolve().parent / "block_oracle.py"
    spec = importlib.util.spec_from_file_location("block_oracle_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBlockOracle(unittest.TestCase):
    def test_parse(self) -> None:
        bo = _load_block_oracle()
        text = "# block number 0\nfoo\n# block number 1\n"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.log"
            p.write_text(text, encoding="utf-8")
            info = bo.parse_block_log(p)
            self.assertTrue(info["exists"])
            self.assertEqual(info["block_marks"], 2)
            self.assertEqual(info["max_block"], 1)
            ok, detail, _ = bo.assert_block_activity(p, min_lines=0)
            self.assertTrue(ok, detail)
            ok2, detail2, _ = bo.assert_block_activity(p, min_lines=1)
            self.assertTrue(ok2, detail2)


if __name__ == "__main__":
    unittest.main()
