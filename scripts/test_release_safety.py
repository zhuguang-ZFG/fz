"""签核必须绑定当前代码和真实结构化证据，夹具不污染现役报告。"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch

ROOT = Path(os.environ.get("FZ_TEST_ROOT", Path(__file__).resolve().parents[1]))
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
spec = importlib.util.spec_from_file_location("honesty_under_test", ROOT / "scripts/release_honesty.py")
rh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rh)
from g3_evidence import G3A_IDS, PAPER_IDS, KEY_IDS, SEG_IDS
from g4_ota import REQUIRED_WHEN_OTA


class ReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.sha = "a" * 40
        self.gate = {"overall_status": "pass", "profile": "standard", "run_state": "completed",
                     "code_identity": {key: {"sha": self.sha, "dirty": False} for key in ("fz", "grbl")},
                     "layers": [{"id": "wokwi_startup", "status": "pass"}]}
        self.scope = self.root / "scope.json"
        self.scope_data = {"version": "release-1", "features": {"paper_path": False, "bluetooth": False, "ota": True},
                           "grbl_git_sha": self.sha, "fz_git_sha": self.sha}
        self.evidence = self.root / "evidence.json"
        (self.root / "capture.log").write_text("device boot and acceptance record\n", encoding="utf-8")
        self.data = {"version": "release-1", "operator": "tester", "date": "2026-10-08",
                     "grbl_git_sha": self.sha, "board": "esp32dev", "machine": "test_drive",
                     "firmware_banner": "Grbl 1.3a", "from_version": "1.0.32", "to_version": "1.0.33",
                     "artifact_sha256_16": "1234567890abcdef", "items": [
                         {"id": item, "result": "pass", "evidence": "capture.log"}
                         for item in REQUIRED_WHEN_OTA]}
        for name, value in (("FZ_ROOT", self.root), ("RESULTS", self.results)):
            context = patch.object(rh, name, value)
            context.start()
            self.addCleanup(context.stop)
        for name, value in (("_git_head", self.sha), ("_git_dirty", False)):
            context = patch.object(rh, name, return_value=value, create=True)
            context.start()
            self.addCleanup(context.stop)
        context = patch.dict(os.environ, {"GRBL_ROOT": str(self.root), "G3_EVIDENCE": "", "G4_EVIDENCE": ""})
        context.start()
        self.addCleanup(context.stop)

    def run_check(self, extra=(), raw=None, scope_path=None, scope_raw=None):
        (self.results / "agent_gate_last.json").write_text(json.dumps(self.gate), encoding="utf-8")
        self.scope.write_text(json.dumps(self.scope_data) if scope_raw is None else scope_raw, encoding="utf-8")
        self.evidence.write_text(json.dumps(self.data) if raw is None else raw, encoding="utf-8")
        output = self.results / "honesty.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = rh.main(["--require-agent-gate", "--scope", str(scope_path or self.scope),
                            "--g4-evidence", str(self.evidence), "--g3-evidence", str(self.evidence),
                            "--out", str(output), *extra])
        return code, json.loads(output.read_text(encoding="utf-8"))

    def assert_blocked(self, **kwargs):
        code, report = self.run_check(**kwargs)
        self.assertNotEqual(code, 0, report)
        self.assertEqual(report["verdict"], "blocked", report)
        self.assertTrue(report["blockers"], report)

    def test_complete_ota_evidence_can_sign(self):
        code, report = self.run_check()
        self.assertEqual(code, 0, report)
        self.assertEqual(report["verdict"], "ready_to_sign", report)
        self.assertTrue(report["hil_required"])

    def test_changed_or_unknown_current_tree_blocks(self):
        for dirty in (True, None):
            with self.subTest(dirty=dirty), patch.object(rh, "_git_dirty", return_value=dirty):
                self.assert_blocked()

    def test_unknown_current_identity_blocks_signoff(self):
        with patch.object(rh, "_git_head", return_value=None):
            self.assert_blocked()

    def test_missing_scope_cannot_disable_hil(self):
        self.assert_blocked(scope_path=self.root / "missing.yaml")

    def test_invalid_scope_types_do_not_disable_hil(self):
        for features in (None, [], {}, {"ota": "false"}, {"ota": 0}, {"ota": True}):
            with self.subTest(features=features):
                self.scope_data["features"] = features
                self.assert_blocked(extra=("--allow-pending-hil",))

    def test_empty_template_or_broken_evidence_rejected(self):
        for raw in ("", "result: pass\n", "[]", "items: [", "TODO\nresult: pass\n"):
            with self.subTest(raw=raw):
                self.assert_blocked(raw=raw)

    def test_evidence_metadata_cannot_be_blank_or_sample(self):
        original = dict(self.data)
        for field, value in (("operator", ""), ("operator", "ci-sample"), ("date", "tomorrow"),
                             ("grbl_git_sha", "b" * 40), ("version", "product-YYYYMMDD"),
                             ("artifact_sha256_16", "")):
            with self.subTest(field=field):
                self.data = {**original, field: value}
                self.assert_blocked()

    def test_required_item_and_nonempty_log_are_checked(self):
        original = json.loads(json.dumps(self.data))
        variants = [[], original["items"][:-1], original["items"] + [original["items"][0]]]
        for items in variants:
            with self.subTest(items=items):
                self.data = {**original, "items": items}
                self.assert_blocked()
        for result, evidence in (("fail", "capture.log"), ("skip", "capture.log"),
                                 ("pass", "n/a"), ("pass", "missing.log"), ("pass", "evidence.json")):
            with self.subTest(result=result, evidence=evidence):
                self.data = json.loads(json.dumps(original))
                self.data["items"][0].update(result=result, evidence=evidence)
                self.assert_blocked()
        self.data = original
        (self.root / "capture.log").write_text("", encoding="utf-8")
        self.assert_blocked()

    def test_g3_required_items_use_existing_contract(self):
        self.scope_data["features"] = {"paper_path": True, "bluetooth": False, "ota": False}
        self.data["items"] = [{"id": rid, "result": "pass", "evidence": "capture.log"}
                              for rid in (*G3A_IDS, *PAPER_IDS, *KEY_IDS, *SEG_IDS)]
        self.assertEqual(self.run_check()[1]["verdict"], "ready_to_sign")
        self.data["items"].pop()
        self.assert_blocked()

    def test_pending_hil_is_never_verified(self):
        code, report = self.run_check(extra=("--allow-pending-hil",), raw="")
        self.assertEqual(code, 0, report)
        self.assertEqual(report["verdict"], "ready_to_sign_pending_hil")
        self.assertFalse(report["hil_ok"])

    def test_optional_cloud_failure_remains_visible(self):
        for status in ("fail", "skip"):
            with self.subTest(status=status):
                self.gate["layers"] = [{"id": "wokwi_startup", "status": status, "blocking": False}]
                code, report = self.run_check()
                self.assertEqual(code, 0, report)
                self.assertTrue(any("wokwi" in warning.lower() for warning in report["warnings"]), report)

    def test_blocking_layer_cannot_hide_behind_overall_pass(self):
        self.gate["layers"] = [{"id": "wokwi_startup", "status": "fail", "blocking": True}]
        self.assert_blocked()

    def test_running_gate_cannot_be_signed(self):
        self.gate["run_state"] = "running"
        self.assert_blocked()

    def test_empty_invalid_duplicate_scope_rejected(self):
        for raw in ("", "features: [", "features: []", "features:\n  ota: true\n  ota: false\n",
                    '{"features":{},"features":{}}', "!!python/object/apply:os.system ['invalid']"):
            with self.subTest(raw=raw):
                self.assert_blocked(scope_raw=raw)

    def test_yaml_features_ignore_comments_and_accept_real_booleans(self):
        text = "# ota: false\nfeatures:\n  ota: yes\n  paper_path: false\n  bluetooth: off\n"
        code, report = self.run_check(scope_raw=text)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["hil_required"])

    def test_malformed_gate_identity_blocks_without_crash(self):
        for identity in (None, [], "invalid", {"fz": [], "grbl": []},
                         {"fz": ["invalid"], "grbl": "invalid"}):
            with self.subTest(identity=identity):
                self.gate["code_identity"] = identity
                self.assert_blocked()

    def test_repository_dirty_probe_covers_worktree_index_and_untracked(self):
        # 使用真实Git状态验证，不仅依赖布尔替身。
        original_spec = importlib.util.spec_from_file_location("honesty_git_probe", ROOT / "scripts/release_honesty.py")
        original = importlib.util.module_from_spec(original_spec)
        original_spec.loader.exec_module(original)
        repo = self.root / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)
        git("init", "--quiet")
        code = repo / "code.py"
        code.write_text("value=1\n")
        git("add", "code.py")
        git("-c", "user.name=Local test", "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "fixture")
        sha = original._git_head(repo)
        self.assertIs(original._git_dirty(repo), False)
        code.write_text("value=2\n")
        self.assertIs(original._git_dirty(repo), True)
        git("add", "code.py")
        self.assertIs(original._git_dirty(repo), True)
        code.write_text("value=1\n")
        git("add", "code.py")
        (repo / "new.py").write_text("value=3\n")
        self.assertIs(original._git_dirty(repo), True)
        self.assertEqual(original._git_head(repo), sha)


if __name__ == "__main__":
    unittest.main()
