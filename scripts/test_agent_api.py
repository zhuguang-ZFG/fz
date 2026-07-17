#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FZ_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("agent_api", FZ_ROOT / "scripts" / "agent_api.py")
assert SPEC and SPEC.loader
API = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(API)


class TestAgentApi(unittest.TestCase):
    def test_console_streams_are_forced_to_utf8(self) -> None:
        stream = mock.Mock()
        with mock.patch.object(API.sys, "stdin", stream), mock.patch.object(
            API.sys, "stdout", stream
        ), mock.patch.object(API.sys, "stderr", stream):
            API._configure_console_encoding()
        self.assertEqual(stream.reconfigure.call_count, 3)
        stream.reconfigure.assert_called_with(encoding="utf-8", errors="replace")

    def test_describe_is_mcp_ready(self) -> None:
        response = API.handle({"request_id": "r1", "operation": "describe"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "r1")
        self.assertIn("run_gate", response["result"]["mcp_mapping"]["tools"])
        self.assertIn("read_report", response["result"]["mcp_mapping"]["resources"])
        self.assertIn("paper_path_verified", response["claims_forbidden"])
        self.assertEqual(
            response["result"]["operations"]["run_gate"]["properties"]["profile"]["enum"],
            list(API.PROFILES),
        )

    def test_lists_cases_without_starting_simulator(self) -> None:
        response = API.handle({"operation": "list_cases", "params": {"domain": "all"}})
        self.assertTrue(response["ok"])
        self.assertTrue(any(case["name"] == "undefined_feed" for case in response["result"]["protocol"]))
        self.assertTrue(any(case["name"] == "json_move_x10_step_window" for case in response["result"]["hardware"]))
        paths = [case["path"] for cases in response["result"].values() for case in cases]
        self.assertTrue(all("\\" not in path for path in paths))

    def test_rejects_unknown_case_before_subprocess(self) -> None:
        with mock.patch.object(API, "_run") as run:
            response = API.handle(
                {"operation": "rerun_cases", "params": {"protocol": ["../../bad"]}}
            )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "unknown_case")
        run.assert_not_called()

    def test_run_gate_uses_fixed_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            report = results / "gate.json"
            report.write_text(json.dumps({"overall_status": "pass"}), encoding="utf-8")
            with mock.patch.object(API, "RESULTS", results), mock.patch.object(API, "LOCK_PATH", results / "lock"), mock.patch.dict(API.REPORTS, {"gate": report}), mock.patch.object(
                API, "_run", return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""}
            ) as run:
                response = API.handle(
                    {"operation": "run_gate", "params": {"profile": "quick", "timeout_s": 10}}
                )
            self.assertTrue(response["ok"])
            command, timeout = run.call_args.args
            self.assertEqual(command[-2:], ["--profile", "quick"])
            self.assertEqual(timeout, 10.0)

    def test_busy_lock_is_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "lock"
            lock.write_text(json.dumps({"request_id": "existing"}), encoding="utf-8")
            with mock.patch.object(API, "LOCK_PATH", lock):
                response = API.handle(
                    {"operation": "run_gate", "params": {"profile": "quick", "timeout_s": 10}}
                )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "busy")
        self.assertEqual(response["error"]["details"]["request_id"], "existing")

    def test_malformed_lock_is_conservative_busy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "lock"
            lock.write_text("not-json", encoding="utf-8")
            with mock.patch.object(API, "LOCK_PATH", lock), mock.patch.object(API, "_run") as run:
                response = API.handle(
                    {"operation": "run_gate", "params": {"profile": "quick", "timeout_s": 10}}
                )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "busy")
        run.assert_not_called()

    def test_stale_lock_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            lock = results / "lock"
            lock.write_text(
                json.dumps({"request_id": "stale", "pid": 2147483647}), encoding="utf-8"
            )
            report = results / "gate.json"
            report.write_text(json.dumps({"overall_status": "pass"}), encoding="utf-8")
            with mock.patch.object(API, "RESULTS", results), mock.patch.object(
                API, "LOCK_PATH", lock
            ), mock.patch.dict(API.REPORTS, {"gate": report}), mock.patch.object(
                API,
                "_run",
                return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
            ):
                response = API.handle(
                    {"operation": "run_gate", "params": {"profile": "quick", "timeout_s": 10}}
                )
            self.assertTrue(response["ok"])
            self.assertFalse(lock.exists())

    def test_report_names_are_whitelisted(self) -> None:
        response = API.handle(
            {"operation": "read_report", "params": {"name": "../../secrets"}}
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "invalid_request")

    def test_product_trace_uses_fixed_boolean_flags(self) -> None:
        report = API.REPORTS["protocol_decision_trace"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        with mock.patch.object(
            API,
            "_run",
            return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
        ) as run:
            response = API.handle(
                {
                    "operation": "run_product_trace",
                    "params": {
                        "paper_running": True,
                        "modal_motion_active": True,
                        "stateful_modal": True,
                        "timeout_s": 10,
                    },
                }
            )
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertEqual(
            command[-3:],
            ["--paper-running", "--modal-motion-active", "--stateful-modal"],
        )
        self.assertEqual(timeout, 10.0)

    def test_differential_rejects_non_boolean_flag(self) -> None:
        with mock.patch.object(API, "_run") as run:
            response = API.handle(
                {"operation": "run_differential", "params": {"paper_running": "false"}}
            )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "invalid_request")
        run.assert_not_called()

    def test_lists_whitelisted_protocol_scenarios(self) -> None:
        response = API.handle({"operation": "list_scenarios"})
        self.assertTrue(response["ok"])
        self.assertTrue(any(item["name"] == "paper_modal_sequence" for item in response["result"]))
        self.assertTrue(all("\\" not in item["path"] for item in response["result"]))

    def test_run_scenarios_uses_discovered_file_stem(self) -> None:
        report = API.REPORTS["protocol_scenarios"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        with mock.patch.object(
            API,
            "_run",
            return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
        ) as run:
            response = API.handle(
                {
                    "operation": "run_scenarios",
                    "params": {"names": ["paper_modal_sequence"], "shrink": False, "timeout_s": 10},
                }
            )
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertEqual(command[-3:], ["--only", "paper_modal_sequence", "--no-shrink"])
        self.assertEqual(timeout, 10.0)

    def test_unknown_scenario_is_rejected_before_subprocess(self) -> None:
        with mock.patch.object(API, "_run") as run:
            response = API.handle(
                {"operation": "run_scenarios", "params": {"names": ["../../bad"]}}
            )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "unknown_case")
        run.assert_not_called()
    def test_run_paper_plant_uses_request_scoped_report(self) -> None:
        canonical = API.REPORTS["paper_plant"]
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(json.dumps({"status": "pass", "coverage": {"ratio": 1.0}}), encoding="utf-8")
        request_id = "../../paper-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "paper_plant_requests" / f"{report_key}.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "cases": [{"fault": "jam"}]}), encoding="utf-8")
        with mock.patch.object(
            API,
            "_run",
            return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
        ) as run:
            response = API.handle(
                {"request_id": request_id, "operation": "run_paper_plant", "params": {"profiles": ["jam", "sensor_bounce"], "timeout_s": 10}}
            )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["cases"][0]["fault"], "jam")
        self.assertEqual(json.loads(canonical.read_text(encoding="utf-8"))["coverage"]["ratio"], 1.0)
        command, timeout = run.call_args.args
        self.assertIn(str(request_report), command)
        self.assertEqual(command[-4:], ["--only", "jam", "--only", "sensor_bounce"])
        self.assertEqual(timeout, 10.0)

    def test_unknown_paper_profile_is_rejected(self) -> None:
        with mock.patch.object(API, "_run") as run:
            response = API.handle(
                {"operation": "run_paper_plant", "params": {"profiles": ["../../shell"]}}
            )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "unknown_case")
        run.assert_not_called()

    def test_lists_qwen_profiles(self) -> None:
        response = API.handle({"operation": "list_qwen_profiles"})
        self.assertTrue(response["ok"])
        self.assertIn("motion_contract", response["result"]["profiles"])
        self.assertEqual(response["result"]["qwen_root_env"], "QWEN_ROOT")

    def test_run_qwen_gate_uses_fixed_profile_and_root(self) -> None:
        report = API.REPORTS["qwen_gate"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        with mock.patch.object(API, "_run", return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""}) as run, mock.patch.dict(API.os.environ, {"QWEN_ROOT": "D:/QWEN3.0"}):
            response = API.handle({"request_id": "q1", "operation": "run_qwen_gate", "params": {"profile": "motion_contract", "timeout_s": 10}})
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertIn("qwen_evidence_adapter.py", command[1])
        self.assertIn("motion_contract", command)
        self.assertEqual(timeout, 40.0)

    def test_unknown_qwen_profile_is_rejected(self) -> None:
        with mock.patch.object(API, "_run") as run:
            response = API.handle({"operation": "run_qwen_gate", "params": {"profile": "shell"}})
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "invalid_request")
        run.assert_not_called()
if __name__ == "__main__":
    unittest.main()
