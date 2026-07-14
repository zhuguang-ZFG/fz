#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestGoldenRecord(unittest.TestCase):
    def test_from_case_dry(self) -> None:
        src = FZ / "protocol_sim" / "cases" / "fail" / "undefined_feed.json"
        r = subprocess.run(
            [
                sys.executable,
                str(FZ / "scripts" / "golden_record.py"),
                "--from-case",
                str(src),
                "--dry-run",
            ],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr + r.stdout)
        self.assertIn("DRY", r.stdout)

    def test_from_last_pass_writes(self) -> None:
        last = FZ / "protocol_sim" / "results" / "last_report.json"
        if not last.is_file():
            self.skipTest("no last_report")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            r = subprocess.run(
                [
                    sys.executable,
                    str(FZ / "scripts" / "golden_record.py"),
                    "--from-last",
                    "--kinds",
                    "pass",
                    "--only",
                    "smoke_ok",
                    "--out-dir",
                    str(out),
                ],
                cwd=str(FZ),
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
            files = list(out.glob("*.json"))
            self.assertGreaterEqual(len(files), 1)
            data = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertTrue(data.get("steps"))
            self.assertEqual(data["steps"][0].get("expect"), "ok")


class TestSoftAllowlist(unittest.TestCase):
    def test_current_div_passes(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "soft_allowlist.py"), "--require-div"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        # may skip if no div file
        if "missing" in (r.stderr + r.stdout).lower() and r.returncode == 2:
            self.skipTest("no soft_divergence")
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        rep = FZ / "protocol_sim" / "results" / "soft_allowlist_last.json"
        self.assertTrue(rep.is_file())
        data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertTrue(data.get("passed"))

    def test_unknown_high_fails(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "soft_allowlist.py"
        spec = importlib.util.spec_from_file_location("soft_allowlist", path)
        assert spec and spec.loader
        sa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sa)

        div = {
            "files": [
                {
                    "name": "soft:totally_unknown_product.nc",
                    "ok_lines": 1,
                    "err_lines": 9,
                }
            ],
            "high_divergence": ["soft:totally_unknown_product.nc"],
        }
        allow = {
            "high_ratio_threshold": 0.5,
            "entries": [{"match": "parsetest_comments", "max_err_ratio": 1.0}],
        }
        rep = sa.check_divergence(div, allow)
        self.assertFalse(rep["passed"])
        self.assertEqual(len(rep["unknown_high"]), 1)


if __name__ == "__main__":
    unittest.main()
