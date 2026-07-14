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

if __name__ == "__main__":
    unittest.main()
