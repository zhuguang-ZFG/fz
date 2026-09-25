#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

FZ = Path(__file__).resolve().parent.parent


class TestAgentObserve(unittest.TestCase):
    def _observe_reports(self, gate, **reports):
        from scripts import agent_observe as observe
        reports["agent_gate_last.json"] = gate
        with mock.patch.object(observe, "_read_json", side_effect=lambda path: reports.get(path.name, {})):
            return observe.build_observe()

    def test_startup_failures_route_to_full_gate_without_duplicate_actions(self):
        result = self._observe_reports({"overall_status": "fail", "failures": [
            {"id": "qemu_startup", "status": "fail"},
            {"id": "wokwi_startup", "status": "fail"},
        ]})
        actions = [item["action"] for item in result["findings"] if item["category"] == "layer_fail"]
        self.assertEqual(actions, ["python scripts/agent_gate.py --profile standard"] * 2)
        self.assertEqual(result["next_actions"].count(actions[0]), 1)

    def test_skipped_nopaper_coverage_ignores_previous_paper_report(self):
        gate = {"overall_status": "pass", "layers": [{"id": "native_coverage", "status": "skip"}]}
        report = {"status": "skip", "stderr": "LLVM missing"}
        result = self._observe_reports(gate, **{"coverage_summary.json": report})
        self.assertFalse(any(item["category"] == "native_coverage" for item in result["findings"]))
        gate["layers"][0]["exit_code"] = 2
        result = self._observe_reports(gate, **{"coverage_summary.json": report})
        self.assertTrue(any(item["category"] == "native_coverage" for item in result["findings"]))

    def test_skipped_hardware_cannot_reuse_recent_failure_as_current(self):
        gate = {"overall_status": "pass", "layers": [{"id": "hardware", "status": "skip"}]}
        result = self._observe_reports(gate, **{"triage_last.json": {"hardware_failures": [{"name": "old"}]}})
        failures = [item for item in result["findings"] if item["category"] == "hardware_case"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["severity"], "info")

    def test_cli(self) -> None:
        r = subprocess.run(
            [sys.executable, str(FZ / "scripts" / "agent_observe.py"), "--quiet"],
            cwd=str(FZ),
            capture_output=True,
            text=True,
        )
        # 0 green hard-free, 1 if hard findings
        self.assertIn(r.returncode, (0, 1), msg=r.stdout + r.stderr)
        js = FZ / "results" / "agent_observe_last.json"
        md = FZ / "results" / "agent_observe_last.md"
        self.assertTrue(js.is_file())
        self.assertTrue(md.is_file())
        data = json.loads(js.read_text(encoding="utf-8"))
        self.assertEqual(data.get("suite"), "agent_observe")
        self.assertIn("findings", data)
        self.assertIn("next_actions", data)
        self.assertTrue(len(data["findings"]) >= 1)
        self.assertIn("Agent observe", md.read_text(encoding="utf-8"))
        self.assertGreaterEqual(int(data.get("version") or 0), 3)
        self.assertIn("summary", data)
        self.assertIn("agent_should_prefer_standard", data["summary"])
        self.assertIn("soft_files_with_errors", data["summary"])
        self.assertIn("hardware_cases_in_last_report", data["summary"])

    def test_allowlisted_divergence_helper(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(mod._is_allowlisted("soft:parsetest.nc", {"soft:parsetest.nc"}))
        self.assertFalse(mod._is_allowlisted("soft:new_unknown.nc", {"soft:parsetest.nc"}))

    def test_fail_without_golden_helper(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        missing = mod._fail_stems_without_golden()
        self.assertIsInstance(missing, list)

    def test_paper_interaction_failure_surfaces_minimal_config(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        finding = mod._paper_interaction_finding(
            {
                "status": "fail",
                "minimal_failure": {
                    "config": {"paper": "missing", "drive": "normal"},
                    "violations": ["unsafe_or_missing_completion"],
                },
            }
        )
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "hard")
        self.assertIn("missing", finding["detail"])
        self.assertEqual(finding["action"], "python hardware_sim/run_paper_plant_interactions.py")

    def test_paper_contract_failure_surfaces_drift(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        finding = mod._paper_contract_finding(
            {"status": "fail", "violations": [{"kind": "firmware_drift", "name": "PAPER_SENSOR_TIMEOUT_MS"}]}
        )
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "hard")
        self.assertIn("PAPER_SENSOR_TIMEOUT_MS", finding["detail"])

    def test_paper_transient_failure_surfaces_case_and_window(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        finding = mod._paper_transient_finding(
            {
                "status": "fail",
                "cases": [
                    {
                        "name": "persistent_jam_times_out",
                        "passed": False,
                        "minimal_failure_window": {"start_ms": 1130, "end_ms": 2400},
                    }
                ],
            }
        )
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "hard")
        self.assertIn("persistent_jam_times_out", finding["detail"])

    def test_machine_pin_failure_surfaces_action(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        findings = mod._machine_pin_findings(
            {
                "status": "fail",
                "errors": [{"kind": "uncontracted_pin_macro", "macros": {"NEW_PIN": "GPIO22"}}],
                "next_actions": ["Classify the new pin macro as a role or alias."],
            }
        )
        self.assertEqual(findings[0]["severity"], "hard")
        self.assertIn("NEW_PIN", findings[0]["detail"])
        self.assertIn("Classify", findings[0]["detail"])
        self.assertEqual(findings[0]["action"], "python hardware_sim/run_machine_pin_erc.py")

    def test_machine_pin_pass_surfaces_coverage_and_waivers(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        findings = mod._machine_pin_findings(
            {
                "status": "pass",
                "coverage": {"resolvable_pin_macros": 28, "contracted_pin_macros": 28, "percent": 100.0},
                "waivers": [{}, {}, {}],
            }
        )
        self.assertEqual(findings[0]["severity"], "info")
        self.assertIn("28/28", findings[0]["detail"])
        self.assertIn("waivers=3", findings[0]["detail"])

    def test_machine_pin_mutation_miss_is_hard_failure(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        findings = mod._machine_pin_mutation_findings({"status": "fail", "mutation_score": {"killed": 5, "total": 6}, "failures": [{"name": "physical_pin_collision"}]})
        self.assertEqual(findings[0]["severity"], "hard")
        self.assertIn("physical_pin_collision", findings[0]["detail"])

    def test_machine_pin_mutation_pass_surfaces_score(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        findings = mod._machine_pin_mutation_findings({"status": "pass", "mutation_score": {"killed": 6, "total": 6}})
        self.assertEqual(findings[0]["severity"], "info")
        self.assertIn("6/6", findings[0]["detail"])

    def test_wokwi_auth_failure_is_not_misreported_as_firmware_failure(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        findings = mod._wokwi_startup_findings({"status": "fail", "cloud_error": "unauthorized"}, "fail")
        self.assertEqual(findings[0]["severity"], "hard")
        self.assertIn("authentication", findings[0]["title"])

    def test_prestart_cloud_failure_is_soft_but_firmware_failure_stays_hard(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_observe", FZ / "scripts/agent_observe.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        report = {"status": "fail", "cloud_error": "transport", "blocking": False}
        self.assertEqual(mod._wokwi_startup_findings(report, "fail")[0]["severity"], "soft")
        report["blocking"] = True
        self.assertEqual(mod._wokwi_startup_findings(report, "fail")[0]["severity"], "hard")

    def test_skipped_wokwi_ignores_stale_report(self) -> None:
        import importlib.util

        path = FZ / "scripts" / "agent_observe.py"
        spec = importlib.util.spec_from_file_location("agent_observe", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod._wokwi_startup_findings({"status": "fail"}, "skip"), [])


if __name__ == "__main__":
    unittest.main()
