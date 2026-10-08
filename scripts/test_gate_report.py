"""门禁运行异常不得留下旧pass，缺仓要有显式检查层。"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import time
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get("FZ_TEST_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("gate_under_test", ROOT / "scripts/agent_gate.py")
ag = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ag
spec.loader.exec_module(ag)


class GateFailureTests(unittest.TestCase):
    def test_early_exception_and_interrupt_replace_old_pass(self):
        for error in (RuntimeError("fixture"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / "report.json"
                output.write_text(json.dumps({"overall_status": "pass", "run_id": "old"}))
                with patch.object(ag, "RESULTS", root), patch.object(ag, "_git_changed_paths", side_effect=error), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    try:
                        code = ag.main(["--profile", "quick", "--json-out", str(output)])
                    except (RuntimeError, KeyboardInterrupt):
                        code = 1
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertNotEqual(report["overall_status"], "pass", report)
                self.assertNotEqual(report["run_id"], "old")
                self.assertNotEqual(code, 0)

    def test_missing_grbl_always_records_both_product_layers(self):
        import importlib
        finder = importlib.import_module("sim_common.find_sim")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            captured = []
            def finish(layers, profile, touch, grbl, out, overall, duration, run):
                captured.extend(layers)
                run.publish({"overall_status": "fail", "layers": []})
                return overall
            with patch.object(ag, "RESULTS", root), patch.object(ag, "_git_changed_paths", return_value=[]), \
                    patch.object(finder, "find_sim", return_value=None), patch.object(ag, "_finish", side_effect=finish), \
                    contextlib.redirect_stdout(io.StringIO()):
                ag.main(["--profile", "quick", "--grbl-root", str(root / "missing"), "--json-out", str(output)])
            for name in ("product_profile", "product_host"):
                matches = [row for row in captured if row.id == name]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0].status, "skip")
                self.assertIn("GRBL_ROOT", matches[0].detail)

    def test_product_module_import_failure_is_reported(self):
        import builtins
        original = builtins.__import__
        def broken(name, *args, **kwargs):
            if name == "sim_common.product_profile":
                raise ImportError("fixture")
            return original(name, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            with patch.object(ag, "RESULTS", root), patch.object(ag, "_git_changed_paths", return_value=[]), \
                    patch("builtins.__import__", side_effect=broken), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = ag.main(["--profile", "quick", "--json-out", str(output)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.read_text())["overall_status"], "fail")


class AtomicReportTests(unittest.TestCase):
    def load(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import gate_report
        return gate_report

    def test_atomic_replace_failure_keeps_complete_previous_document(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            module.atomic_write_json(path, {"version": 1})
            with patch.object(module.os, "replace", side_effect=OSError("fixture")), self.assertRaises(OSError):
                module.atomic_write_json(path, {"version": 2})
            self.assertEqual(json.loads(path.read_text()), {"version": 1})
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_running_and_completion_share_identity(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "report.json"
            with module.GateRun(path, root / "gate.lock") as run:
                initial = json.loads(path.read_text())
                self.assertEqual(initial["overall_status"], "running")
                run.publish({"overall_status": "pass"})
            final = json.loads(path.read_text())
            self.assertEqual(final["run_id"], initial["run_id"])
            self.assertEqual(final["run_state"], "completed")

    def test_second_runner_cannot_overwrite_active_report(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, lock = root / "report.json", root / "gate.lock"
            with module.GateRun(path, lock) as first:
                before = path.read_bytes()
                with self.assertRaises(RuntimeError):
                    with module.GateRun(path, lock):
                        self.fail("不能获得活动门禁锁")
                self.assertEqual(path.read_bytes(), before)
                first.publish({"overall_status": "pass"})
            with module.GateRun(path, lock) as second:
                second.publish({"overall_status": "pass"})

    def test_return_without_final_report_is_failure(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with module.GateRun(root / "report.json", root / "gate.lock"):
                pass
            self.assertEqual(json.loads((root / "report.json").read_text())["overall_status"], "fail")

    def test_process_kill_keeps_nonpass_and_releases_lock(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, lock = root / "report.json", root / "gate.lock"
            code = "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from gate_report import GateRun; " \
                   "run=GateRun(Path(sys.argv[2]),Path(sys.argv[3])); run.__enter__(); sys.stdin.read(1)"
            child = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "scripts"), str(output), str(lock)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not output.is_file() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(output.is_file())
                child.kill()
                child.communicate(timeout=5)
                self.assertEqual(json.loads(output.read_text())["overall_status"], "running")
                with module.GateRun(output, lock) as run:
                    run.publish({"overall_status": "pass"})
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
