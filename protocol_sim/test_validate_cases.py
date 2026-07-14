#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from validate_cases import validate_all, validate_case_file  # noqa: E402


class TestValidateCases(unittest.TestCase):
    def test_repo_cases_ok(self) -> None:
        code, errors, rep = validate_all()
        self.assertEqual(code, 0, msg="\n".join(errors[:20]))
        self.assertGreaterEqual(rep["n_files"], 10)
        self.assertTrue(rep["passed"])

    def test_bad_step_caught(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(
                json.dumps({"name": "x", "steps": [{"send": "G0", "expect": "nope"}]}),
                encoding="utf-8",
            )
            errs = validate_case_file(p, "fail")
            self.assertTrue(any("expect" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
