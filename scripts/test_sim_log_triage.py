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


class TestSimLogTriage(unittest.TestCase):
    def test_cli_writes_files(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "sim_log_triage.py")],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        md = FZ / "results" / "triage_last.md"
        js = FZ / "results" / "triage_last.json"
        self.assertTrue(md.is_file())
        self.assertTrue(js.is_file())
        data = json.loads(js.read_text(encoding="utf-8"))
        self.assertEqual(data.get("suite"), "sim_log_triage")
        self.assertIn("Host SIL triage", md.read_text(encoding="utf-8"))

    def test_build_from_synthetic_report(self) -> None:
        # Import module
        import importlib.util

        path = FZ / "scripts" / "sim_log_triage.py"
        spec = importlib.util.spec_from_file_location("sim_log_triage", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        t = mod.build_triage()
        self.assertIn("log_paths", t)
        md = mod.render_md(t)
        self.assertIn("triage", md.lower() or "Host")


if __name__ == "__main__":
    unittest.main()
