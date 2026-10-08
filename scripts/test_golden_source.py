"""金样来源只能精确且无歧义；测试不依赖生产last_report。"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import golden_record as recorder


class GoldenSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fail_dir = self.root / "fail"
        self.status = self.root / "status"
        self.golden = self.root / "golden"
        for path in (self.fail_dir, self.status, self.golden): path.mkdir()
        patcher = patch.multiple(recorder, FZ_ROOT=self.root, FAIL_DIR=self.fail_dir,
                                 STATUS_DIR=self.status, GOLDEN_DIR=self.golden)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, data, directory=None):
        path = (directory or self.fail_dir) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_substring_cannot_choose_source(self):
        self.write("stop.json", {"name": "stop"})
        self.assertIsNone(recorder._find_source_json("stop_large"))
        self.assertIsNone(recorder._find_source_json("sto"))

    def test_missing_and_empty_names_cannot_match_everything(self):
        for data in ({}, {"name": ""}, {"name": None}, {"name": "  "}):
            with self.subTest(data=data):
                self.write("unrelated.json", data)
                self.assertIsNone(recorder._find_source_json("actual_case"))

    def test_empty_requested_identity_is_rejected(self):
        self.write("stop.json", {"name": "stop"})
        self.assertIsNone(recorder._find_source_json(""))
        self.assertIsNone(recorder._find_source_json("   "))

    def test_filename_and_explicit_name_match_exactly(self):
        path = self.write("undefined_feed.json", {"name": "undefined_feed_G1"})
        self.assertEqual(recorder._find_source_json("UNDEFINED_FEED.json"), path)
        self.assertEqual(recorder._find_source_json("undefined_feed_G1"), path)

    def test_ambiguous_metadata_names_fail_closed(self):
        self.write("first.json", {"name": "shared"})
        self.write("second.json", {"name": "shared"}, self.status)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            recorder._find_source_json("shared")

    def test_filename_and_metadata_conflict_is_ambiguous(self):
        self.write("shared.json", {"name": "first"})
        self.write("second.json", {"name": "shared"}, self.status)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            recorder._find_source_json("shared")

    def test_unrelated_bad_json_does_not_break_lookup(self):
        (self.fail_dir / "broken.json").write_text("{", encoding="utf-8")
        path = self.write("valid.json", {"name": "valid"})
        self.assertEqual(recorder._find_source_json("valid"), path)

    def test_exact_bad_json_is_not_promoted(self):
        (self.fail_dir / "broken.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError): recorder._find_source_json("broken")

    def test_matching_source_preserves_setup(self):
        self.write("source.json", {"name": "exact", "setup": ["G90"], "steps": [{"send": "G1 X1", "expect": "ok"}]})
        result = recorder.golden_from_fail_or_status({"name": "exact"})
        self.assertEqual(result["setup"], ["G90"])
        self.assertEqual(result["steps"][0]["send"], "G1 X1")

    def test_missing_report_identity_cannot_select_generic_case(self):
        self.write("case.json", {"name": "case", "setup": ["G90"], "steps": []})
        for name in (None, "", "   ", 123):
            with self.subTest(name=name), self.assertRaises(ValueError):
                recorder.golden_from_fail_or_status({"name": name})

    def test_cli_ambiguity_writes_no_golden(self):
        self.write("first.json", {"name": "shared"})
        self.write("second.json", {"name": "shared"}, self.status)
        report = self.root / "report.json"
        report.write_text(json.dumps([{"name": "shared", "kind": "fail", "passed": True, "lines": []}]), encoding="utf-8")
        output = self.root / "output"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = recorder.main(["--from-last", "--kinds", "fail", "--report", str(report), "--out-dir", str(output)])
        self.assertEqual(code, 2)
        self.assertFalse(list(output.glob("*.json")))


if __name__ == "__main__": unittest.main()
