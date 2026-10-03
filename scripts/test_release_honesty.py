#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestReleaseHonesty(unittest.TestCase):
    def test_runs_with_allow_pending(self) -> None:
        r = subprocess.run(
            [
                sys.executable,
                str(FZ / "scripts" / "release_honesty.py"),
                "--require-agent-gate",
                "--allow-pending-hil",
                "--max-age-hours",
                "7200",
            ],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        # 0 if gate pass exists; 1 if blocked
        self.assertIn(r.returncode, (0, 1), msg=r.stdout + r.stderr)
        rep = FZ / "results" / "release_honesty_last.json"
        self.assertTrue(rep.is_file())
        data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(data["suite"], "release_honesty")
        self.assertIn(data["verdict"], (
            "ready_for_dev",
            "ready_to_sign",
            "ready_to_sign_pending_hil",
            "blocked",
        ))

    def test_forbidden_claims(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "notes.md"
            p.write_text("纸路已验证，可以发版\n", encoding="utf-8")
            r = subprocess.run(
                [
                    sys.executable,
                    str(FZ / "scripts" / "release_honesty.py"),
                    "--allow-pending-hil",
                    "--max-age-hours",
                    "9999",
                    "--claims-file",
                    str(p),
                ],
                cwd=str(FZ),
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 1, msg=r.stdout)
            data = json.loads(
                (FZ / "results" / "release_honesty_last.json").read_text(encoding="utf-8")
            )
            self.assertIn("paper_path_verified", data.get("forbidden_claims_hit") or [])



    def test_stale_report_blocker(self) -> None:
        """Stale agent_gate report (old mtime) should block with --require-agent-gate."""
        gate_path = FZ / "results" / "agent_gate_last.json"
        backup = None
        if gate_path.is_file():
            backup = gate_path.read_bytes()
        try:
            # Fake a very old pass report
            fake = {"overall_status": "pass", "profile": "quick", "generated_at": "2020-01-01T00:00:00"}
            gate_path.write_text(json.dumps(fake), encoding="utf-8")
            old_ts = time.time() - 48 * 3600  # 48 hours ago
            os.utime(gate_path, (old_ts, old_ts))

            r = subprocess.run(
                [
                    sys.executable,
                    str(FZ / "scripts" / "release_honesty.py"),
                    "--require-agent-gate",
                    "--max-age-hours",
                    "1",
                ],
                cwd=str(FZ),
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 1, msg=r.stdout + r.stderr)
            data = json.loads(
                (FZ / "results" / "release_honesty_last.json").read_text(encoding="utf-8")
            )
            self.assertIn("blocked", data["verdict"])
            self.assertTrue(
                any("too old" in b for b in data["blockers"]),
                msg=f"no 'too old' in blockers: {data['blockers']}",
            )
        finally:
            if backup is not None:
                gate_path.write_bytes(backup)
            else:
                gate_path.unlink(missing_ok=True)

class TestCodeIdentityBinding(unittest.TestCase):
    """必修#2：门禁报告必须绑在代码版本上，mtime 窗口挡不住「代码已变」的旧 pass。"""

    def _load(self):
        import importlib.util

        path = FZ / "scripts" / "release_honesty.py"
        spec = importlib.util.spec_from_file_location("release_honesty_mod", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_sha_mismatch_blocks(self) -> None:
        rh = self._load()
        gate = {"code_identity": {"fz": {"sha": "a" * 40, "dirty": False},
                                  "grbl": {"sha": "b" * 40, "dirty": False}}}
        found = rh.check_code_identity(gate, {"fz": "c" * 40, "grbl": "b" * 40})
        self.assertTrue(any("代码已变动" in b for b in found["blockers"]), found)

    def test_matching_sha_passes(self) -> None:
        rh = self._load()
        gate = {"code_identity": {"fz": {"sha": "a" * 40, "dirty": False},
                                  "grbl": {"sha": "b" * 40, "dirty": False}}}
        found = rh.check_code_identity(gate, {"fz": "a" * 40, "grbl": "b" * 40})
        self.assertEqual(found["blockers"], [])

    def test_legacy_report_without_identity_blocks(self) -> None:
        rh = self._load()
        found = rh.check_code_identity({"overall_status": "pass"}, {"fz": "a" * 40, "grbl": None})
        self.assertTrue(any("code_identity" in b for b in found["blockers"]), found)

    def test_dirty_tree_blocks_only_on_explicit_sign_off(self) -> None:
        rh = self._load()
        gate = {"code_identity": {"fz": {"sha": "a" * 40, "dirty": True}, "grbl": {}}}
        dev = rh.check_code_identity(gate, {"fz": "a" * 40, "grbl": None})
        self.assertEqual(dev["blockers"], [])
        self.assertTrue(any("脏" in w for w in dev["warnings"]), dev)
        sign = rh.check_code_identity(gate, {"fz": "a" * 40, "grbl": None}, sign_off=True)
        self.assertTrue(any("脏" in b for b in sign["blockers"]), sign)

    def test_scope_declared_sha_must_match_report(self) -> None:
        rh = self._load()
        gate = {"code_identity": {"fz": {"sha": "a" * 40, "dirty": False},
                                  "grbl": {"sha": "b" * 40, "dirty": False}}}
        scope = 'grbl_git_sha: "deadbeef"\n'
        found = rh.check_code_identity(
            gate, {"fz": "a" * 40, "grbl": "b" * 40}, scope_raw=scope
        )
        self.assertTrue(any("scope 声明" in b for b in found["blockers"]), found)
        ok = rh.check_code_identity(
            gate, {"fz": "a" * 40, "grbl": "b" * 40}, scope_raw=f"grbl_git_sha: {'b' * 12}\n"
        )
        self.assertEqual(ok["blockers"], [])

    def test_end_to_end_mismatched_report_is_blocked(self) -> None:
        """整链：伪造一份 sha 不符的新鲜 pass 报告，--require-agent-gate 必须判 blocked。"""
        gate_path = FZ / "results" / "agent_gate_last.json"
        backup = gate_path.read_bytes() if gate_path.is_file() else None
        try:
            gate_path.parent.mkdir(parents=True, exist_ok=True)
            gate_path.write_text(
                json.dumps(
                    {
                        "overall_status": "pass",
                        "profile": "standard",
                        "generated_at": "2026-09-27T00:00:00+00:00",
                        "run_id": "deadbeef",
                        "code_identity": {
                            "fz": {"sha": "0" * 40, "branch": "main", "dirty": False},
                            "grbl": {"sha": None, "branch": None, "dirty": None},
                        },
                    }
                ),
                encoding="utf-8",
            )
            r = subprocess.run(
                [
                    sys.executable,
                    str(FZ / "scripts" / "release_honesty.py"),
                    "--require-agent-gate",
                    "--allow-pending-hil",
                    "--max-age-hours",
                    "99999",
                ],
                cwd=str(FZ),
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 1, msg=r.stdout + r.stderr)
            data = json.loads(
                (FZ / "results" / "release_honesty_last.json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["verdict"], "blocked")
            self.assertFalse(data["code_identity_ok"])
            self.assertTrue(
                any("代码已变动" in b for b in data["blockers"]), msg=str(data["blockers"])
            )
        finally:
            if backup is not None:
                gate_path.write_bytes(backup)
            else:
                gate_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
