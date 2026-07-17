#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import run_protocol_campaign as campaign
from protocol_model import simulate


class TestXiaozhiProtocolCampaign(unittest.TestCase):
    def test_campaign_covers_happy_recovery_and_network_faults(self) -> None:
        report = campaign.run_campaign()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(report["cases"]), 10)
        self.assertTrue(all(case["passed"] for case in report["cases"]))
        self.assertTrue(all(case["minimal_failure_events"] for case in report["cases"] if case["outcome"] == "failed"))

    def test_audio_and_mcp_fail_closed(self) -> None:
        audio = simulate([{"kind": "connect"}, {"kind": "uplink_audio", "session_id": "s1"}])
        mcp = simulate([{"kind": "connect"}, campaign.HELLO, {"kind": "mcp_response", "jsonrpc": "2.0", "id": 1, "result": {}}])
        wrong_version = simulate([{"kind": "connect"}, campaign.HELLO, {"kind": "mcp_request", "jsonrpc": "1.0", "id": 1, "method": "initialize"}])
        self.assertEqual(audio["reason"], "session_mismatch")
        self.assertEqual(mcp["reason"], "invalid_mcp_response")
        self.assertEqual(wrong_version["reason"], "invalid_mcp_request")

    def test_hello_ack_matches_product_optional_metadata_behavior(self) -> None:
        missing = simulate([{"kind": "connect"}, {"kind": "hello_ack"}])
        changed = simulate([{"kind": "connect"}, {"kind": "hello_ack", "protocol": "server-v2", "device_id": 7}])
        self.assertEqual((missing["outcome"], missing["state"], missing["session_id"]), ("running", "idle", None))
        self.assertEqual((changed["outcome"], changed["state"], changed["session_id"]), ("running", "idle", None))

    def test_shrinker_keeps_failure_reason(self) -> None:
        events = [{"kind": "connect"}, campaign.HELLO, {"kind": "listen_start", "session_id": "s1", "mode": "manual"}, {"kind": "listen_stop", "session_id": "s1"}, {"kind": "tts_start", "session_id": "s1"}, {"kind": "tts_start", "session_id": "s1"}]
        signature = campaign.failure_signature(simulate(events))
        minimal = campaign.minimize(events, signature)
        self.assertEqual(simulate(minimal)["reason"], "invalid_tts_start")
        self.assertEqual(campaign.failure_signature(simulate(minimal)), signature)
        self.assertLess(len(minimal), len(events))

    def test_incorrect_expectation_must_fail(self) -> None:
        mutant = (("mutant", [{"kind": "connect"}], "running", "", "idle"),)
        with mock.patch.object(campaign, "SCENARIOS", mutant):
            report = campaign.run_campaign()
        self.assertEqual(report["status"], "fail")
        self.assertIn("unexpected_terminal_result", report["cases"][0]["violations"])


if __name__ == "__main__":
    unittest.main()
