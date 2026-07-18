#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


_LIVE_SUBPROCESS = os.environ.get("FZ_AGENT_API_NO_LIVE_SUBPROCESS") != "1"
_SKIP_LIVE = unittest.skipUnless(
    _LIVE_SUBPROCESS,
    "live subprocess spawn disabled (FZ_AGENT_API_NO_LIVE_SUBPROCESS=1)",
)


FZ_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("agent_api", FZ_ROOT / "scripts" / "agent_api.py")
assert SPEC and SPEC.loader
API = importlib.util.module_from_spec(SPEC)
# Register before exec so dataclasses can resolve stringized (PEP 563) annotations,
# which look up cls.__module__ in sys.modules during @dataclass processing.
import sys as _sys
_sys.modules[SPEC.name] = API
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
        self.assertIn("run_machine_pin_erc", response["result"]["mcp_mapping"]["tools"])
        self.assertIn("machine_pin_erc", response["result"]["reports"])
        self.assertIn("xiaozhi_real_audio_verified", response["claims_forbidden"])
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

    def test_run_paper_interactions_uses_request_scoped_report(self) -> None:
        request_id = "interaction-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "paper_plant_requests" / f"{report_key}-interactions.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "configuration_count": 48}), encoding="utf-8")
        with mock.patch.object(
            API,
            "_run",
            return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
        ) as run:
            response = API.handle(
                {"request_id": request_id, "operation": "run_paper_interactions", "params": {"timeout_s": 10}}
            )
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["configuration_count"], 48)
        command, timeout = run.call_args.args
        self.assertEqual(command[-2:], ["--json-out", str(request_report)])
        self.assertEqual(timeout, 10.0)

    def test_run_machine_pin_erc_uses_fixed_runner_and_report(self) -> None:
        request_id = "machine-pin-erc-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "paper_plant_requests" / f"{report_key}-machine-pin-erc.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "errors": []}), encoding="utf-8")
        with mock.patch.object(API, "_run", return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""}) as run:
            response = API.handle({"request_id": request_id, "operation": "run_machine_pin_erc", "params": {"grbl_root": "D:/Users/Grbl_Esp32", "timeout_s": 10}})
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertIn("run_machine_pin_erc.py", command[1])
        self.assertEqual(command[-2:], ["--json-out", str(request_report)])
        self.assertEqual(timeout, 10.0)

    def test_run_paper_contract_uses_fixed_runner_and_report(self) -> None:
        request_id = "contract-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "paper_plant_requests" / f"{report_key}-contract.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "violations": []}), encoding="utf-8")
        with mock.patch.object(
            API,
            "_run",
            return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
        ) as run:
            response = API.handle(
                {"request_id": request_id, "operation": "run_paper_contract", "params": {"grbl_root": "D:/Users/Grbl_Esp32", "timeout_s": 10}}
            )
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertIn("run_paper_firmware_contract.py", command[1])
        self.assertEqual(command[-2:], ["--json-out", str(request_report)])
        self.assertEqual(timeout, 10.0)

    def test_run_paper_transients_uses_request_scoped_report(self) -> None:
        request_id = "transient-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "paper_plant_requests" / f"{report_key}-transients.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "cases": []}), encoding="utf-8")
        with mock.patch.object(
            API,
            "_run",
            return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""},
        ) as run:
            response = API.handle(
                {"request_id": request_id, "operation": "run_paper_transients", "params": {"timeout_s": 10}}
            )
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertIn("run_paper_transient_campaign.py", command[1])
        self.assertEqual(command[-2:], ["--json-out", str(request_report)])
        self.assertEqual(timeout, 10.0)

    def test_lists_qwen_profiles(self) -> None:
        response = API.handle({"operation": "list_qwen_profiles"})
        self.assertTrue(response["ok"])
        self.assertIn("motion_contract", response["result"]["profiles"])
        self.assertIn("voice_contract", response["result"]["profiles"])
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

    def test_run_xiaozhi_protocol_uses_request_scoped_report(self) -> None:
        request_id = "xiaozhi-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "xiaozhi_requests" / f"{report_key}.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "cases": []}), encoding="utf-8")
        with mock.patch.object(API, "_run", return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""}) as run:
            response = API.handle({"request_id": request_id, "operation": "run_xiaozhi_protocol", "params": {"timeout_s": 10}})
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertIn("run_protocol_campaign.py", command[1])
        self.assertEqual(command[-2:], ["--json-out", str(request_report)])
        self.assertEqual(timeout, 10.0)

    def test_run_xiaozhi_contract_uses_qwen_root_and_scoped_report(self) -> None:
        request_id = "xiaozhi-contract-test"
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = API.RESULTS / "xiaozhi_requests" / f"{report_key}-contract.json"
        request_report.parent.mkdir(parents=True, exist_ok=True)
        request_report.write_text(json.dumps({"status": "pass", "violations": []}), encoding="utf-8")
        with mock.patch.object(API, "_run", return_value={"exit_code": 0, "duration_s": 1.0, "stdout_tail": "", "stderr_tail": ""}) as run, mock.patch.dict(API.os.environ, {"QWEN_ROOT": "D:/QWEN3.0"}):
            response = API.handle({"request_id": request_id, "operation": "run_xiaozhi_contract", "params": {"timeout_s": 10}})
        self.assertTrue(response["ok"])
        command, timeout = run.call_args.args
        self.assertIn("run_firmware_contract.py", command[1])
        self.assertIn("D:\\QWEN3.0", command)
        self.assertEqual(command[-2:], ["--json-out", str(request_report)])
        self.assertEqual(timeout, 10.0)
class TestAgentApiRun(unittest.TestCase):
    def test_run_substitutes_base_executable_and_devnull_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_base = Path(directory) / "base-python.exe"
            fake_base.write_bytes(b"")
            with mock.patch.object(API.sys, "_base_executable", str(fake_base), create=True), mock.patch.dict(
                API.os.environ, {"FZ_AGENT_API_BASE_EXECUTABLE": "1"}
            ), mock.patch.object(API.subprocess, "Popen") as popen:
                proc = popen.return_value
                proc.stdout = io.StringIO("out-line\n")
                proc.stderr = io.StringIO("err-line\n")
                proc.wait.return_value = None
                proc.returncode = 0
                result = API._run([API.sys.executable, "-c", "pass"], 5.0)
        command = popen.call_args.args[0]
        self.assertEqual(command[0], str(fake_base))
        self.assertEqual(command[1:], ["-c", "pass"])
        self.assertIs(popen.call_args.kwargs.get("stdin"), API.subprocess.DEVNULL)
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("out-line", result["stdout_tail"])
        self.assertIn("err-line", result["stderr_tail"])

    def test_run_no_substitution_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_base = Path(directory) / "base-python.exe"
            fake_base.write_bytes(b"")
            with mock.patch.object(API.sys, "_base_executable", str(fake_base), create=True), mock.patch.dict(
                API.os.environ, {}, clear=False
            ), mock.patch.object(API.subprocess, "Popen") as popen:
                API.os.environ.pop("FZ_AGENT_API_BASE_EXECUTABLE", None)
                proc = popen.return_value
                proc.stdout = io.StringIO("")
                proc.stderr = io.StringIO("")
                proc.wait.return_value = None
                proc.returncode = 0
                API._run([API.sys.executable, "-c", "pass"], 5.0)
        self.assertEqual(popen.call_args.args[0][0], API.sys.executable)

    def test_run_keeps_explicit_interpreter(self) -> None:
        with mock.patch.object(API.sys, "_base_executable", r"D:\base\python.exe", create=True), mock.patch.object(
            API.subprocess, "Popen"
        ) as popen:
            proc = popen.return_value
            proc.stdout = io.StringIO("")
            proc.stderr = io.StringIO("")
            proc.wait.return_value = None
            proc.returncode = 0
            API._run([r"D:\explicit\python.exe", "runner.py"], 5.0)
        self.assertEqual(popen.call_args.args[0][0], r"D:\explicit\python.exe")

    @_SKIP_LIVE
    def test_run_timeout_kills_process_tree_fast(self) -> None:
        # taskkill execution is mocked (asserted by args): force-killing real
        # process trees in tests trips behavioral EDR rules (spawn+kill chain).
        with mock.patch.object(API.subprocess, "run") as taskkill_run:
            t0 = time.monotonic()
            with self.assertRaises(API.ApiError) as ctx:
                API._run(
                    [API.sys.executable, "-c", "import time; print('mark', flush=True); time.sleep(3)"],
                    1.0,
                )
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 30.0)
        self.assertEqual(ctx.exception.code, "timeout")
        self.assertIn("mark", ctx.exception.details["stdout_tail"])
        if os.name == "nt":
            self.assertEqual(taskkill_run.call_args.args[0][:3], ["taskkill", "/F", "/T"])

    @_SKIP_LIVE
    def test_run_tee_writes_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            result = API._run([API.sys.executable, "-c", "print('hello-tee')"], 10.0, log_path=log)
            self.assertEqual(result["exit_code"], 0)
            self.assertIn("hello-tee", log.read_text(encoding="utf-8"))
            self.assertIn("hello-tee", result["stdout_tail"])

    @_SKIP_LIVE
    def test_run_timeout_details_carry_log_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "run.log"
            with mock.patch.object(API.subprocess, "run"):
                with self.assertRaises(API.ApiError) as ctx:
                    API._run(
                        [API.sys.executable, "-c", "import time; print('pre', flush=True); time.sleep(3)"],
                        1.0,
                        log_path=log,
                    )
            self.assertEqual(ctx.exception.details.get("log_path"), str(log))
            self.assertIn("pre", log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
