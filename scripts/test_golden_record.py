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
        with tempfile.TemporaryDirectory() as td:
            # 本用例只测试录制行为，不依赖上次门禁留下的报告内容或顺序。
            last = Path(td) / "report.json"
            last.write_text(json.dumps([{"name": "smoke_ok", "kind": "pass", "passed": True,
                "lines": [{"line": "G21", "responses": ["ok"]}]}]), encoding="utf-8")
            out = Path(td) / "golden"
            r = subprocess.run(
                [
                    sys.executable,
                    str(FZ / "scripts" / "golden_record.py"),
                    "--from-last",
                    "--report",
                    str(last),
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


class TestSoftAllowlistTightening(unittest.TestCase):
    """必修#3：子串豁免 / max_err_ratio:0 被吞 / 无文件行免检三处放宽通道。"""

    def _mod(self):
        import importlib.util

        path = FZ / "scripts" / "soft_allowlist.py"
        spec = importlib.util.spec_from_file_location("soft_allowlist_tight", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_substring_entry_cannot_blanket_exempt(self) -> None:
        sa = self._mod()
        div = {
            "files": [{"name": "soft:brand_new_sample.nc", "ok_lines": 1, "err_lines": 9}],
            "high_divergence": ["soft:brand_new_sample.nc"],
        }
        # 一条宽 entry（旧双向子串下 'sample' in 'brand_new_sample.nc' 命中）不得豁免
        rep = sa.check_divergence(div, {"entries": [{"match": "sample", "max_err_ratio": 1.0}]})
        self.assertFalse(rep["passed"])
        self.assertEqual(len(rep["unknown_high"]), 1)
        # 短名 entry 反向包含（旧逻辑 'brand_new_sample.nc' in ... 亦可命中）同样不得豁免
        rep2 = sa.check_divergence(div, {"entries": [{"match": "brand", "max_err_ratio": 1.0}]})
        self.assertFalse(rep2["passed"])
        # 逐条精确登记才放行
        rep3 = sa.check_divergence(
            div, {"entries": [{"match": "brand_new_sample", "max_err_ratio": 1.0}]}
        )
        self.assertTrue(rep3["passed"], rep3)

    def test_zero_max_err_ratio_means_zero(self) -> None:
        sa = self._mod()
        div = {
            "files": [{"name": "soft:x.nc", "ok_lines": 1, "err_lines": 9}],
            "high_divergence": ["soft:x.nc"],
        }
        rep = sa.check_divergence(div, {"entries": [{"match": "x", "max_err_ratio": 0}]})
        self.assertFalse(rep["passed"], rep)
        self.assertEqual(len(rep["over_ratio"]), 1)

    def test_high_name_without_file_row_still_passes_ratio_gate(self) -> None:
        sa = self._mod()
        div = {"files": [], "high_divergence": ["soft:ghost.nc"]}
        rep = sa.check_divergence(div, {"entries": [{"match": "ghost", "max_err_ratio": 0.5}]})
        self.assertFalse(rep["passed"], rep)
        self.assertEqual(len(rep["over_ratio"]), 1)
        # 显式允许全分歧（1.0）时才放行
        ok = sa.check_divergence(div, {"entries": [{"match": "ghost", "max_err_ratio": 1.0}]})
        self.assertTrue(ok["passed"], ok)

    def test_shipped_allowlist_still_covers_current_samples(self) -> None:
        """收紧后仓内 allowlist 必须仍精确覆盖现役样本，不得把真分歧变成 unknown。"""
        sa = self._mod()
        allow = sa.load_allowlist(FZ / "protocol_sim" / "cases" / "soft" / "allowlist.yaml")
        div_path = FZ / "protocol_sim" / "results" / "soft_divergence.json"
        if not div_path.is_file():
            self.skipTest("no soft_divergence")
        div = json.loads(div_path.read_text(encoding="utf-8"))
        rep = sa.check_divergence(div, allow)
        self.assertTrue(rep["passed"], msg=json.dumps(rep, ensure_ascii=False)[:800])
        for f in div.get("files") or []:
            with self.subTest(name=f.get("name")):
                self.assertIsNotNone(
                    sa._find_entry(str(f.get("name")), list(allow.get("entries") or [])),
                    msg=f"{f.get('name')} 在收紧后失去 allowlist 覆盖",
                )


if __name__ == "__main__":
    unittest.main()
