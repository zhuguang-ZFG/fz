#!/usr/bin/env python3
"""Run deterministic Xiaozhi protocol and network-fault scenarios."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from protocol_model import simulate

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
HELLO = {"kind": "hello_ack", "protocol": "lima-device-v1", "device_id": "s1"}
S = "s1"
SCENARIOS: Tuple[Tuple[str, List[Dict[str, Any]], str, str, str], ...] = (
    ("manual_voice_roundtrip", [{"kind": "connect"}, HELLO, {"kind": "listen_start", "session_id": S, "mode": "manual"}, {"kind": "uplink_audio", "session_id": S}, {"kind": "listen_stop", "session_id": S}, {"kind": "tts_start", "session_id": S}, {"kind": "downlink_audio", "session_id": S}, {"kind": "tts_stop", "session_id": S}], "running", "", "idle"),
    ("abort_speaking_resumes_listen", [{"kind": "connect"}, HELLO, {"kind": "tts_start", "session_id": S}, {"kind": "abort", "session_id": S}], "running", "", "listening"),
    ("disconnect_reconnect", [{"kind": "connect"}, HELLO, {"kind": "tts_start", "session_id": S}, {"kind": "disconnect"}, {"kind": "connect"}, {**HELLO, "device_id": "s2"}], "running", "", "idle"),
    ("hello_ack_optional_metadata_matches_firmware", [{"kind": "connect"}, {"kind": "hello_ack", "protocol": "server-v2"}], "running", "", "idle"),
    ("mcp_initialize_list_call", [{"kind": "connect"}, HELLO, {"kind": "mcp_request", "jsonrpc": "2.0", "id": 1, "method": "initialize"}, {"kind": "mcp_response", "jsonrpc": "2.0", "id": 1, "result": {}}, {"kind": "mcp_request", "jsonrpc": "2.0", "id": 2, "method": "tools/list"}, {"kind": "mcp_response", "jsonrpc": "2.0", "id": 2, "result": {"tools": []}}, {"kind": "mcp_request", "jsonrpc": "2.0", "id": 3, "method": "tools/call"}, {"kind": "mcp_response", "jsonrpc": "2.0", "id": 3, "error": {"code": -32601}}], "running", "", "idle"),
    ("hello_packet_loss", [{"kind": "connect"}, {"kind": "hello_timeout"}], "failed", "hello_timeout", "disconnected"),
    ("reordered_audio_before_hello", [{"kind": "connect"}, {"kind": "downlink_audio", "session_id": S}, HELLO], "failed", "session_mismatch", "disconnected"),
    ("duplicate_tts_start", [{"kind": "connect"}, HELLO, {"kind": "tts_start", "session_id": S}, {"kind": "tts_start", "session_id": S}], "failed", "invalid_tts_start", "disconnected"),
    ("stale_session_after_reconnect", [{"kind": "connect"}, HELLO, {"kind": "disconnect"}, {"kind": "connect"}, {**HELLO, "device_id": "s2"}, {"kind": "listen_start", "session_id": S, "mode": "auto"}], "failed", "session_mismatch", "disconnected"),
    ("duplicate_mcp_request_id", [{"kind": "connect"}, HELLO, {"kind": "mcp_request", "jsonrpc": "2.0", "id": 7, "method": "tools/call"}, {"kind": "mcp_request", "jsonrpc": "2.0", "id": 7, "method": "tools/call"}], "failed", "invalid_mcp_request", "disconnected"),
)


def failure_signature(report: Dict[str, Any]) -> Tuple[str, str]:
    trace = report.get("trace", [])
    return report.get("reason", ""), trace[-1].get("before", "") if trace else ""


def minimize(events: Sequence[Dict[str, Any]], signature: Tuple[str, str]) -> List[Dict[str, Any]]:
    current = list(events)
    changed = True
    while changed:
        changed = False
        for index in range(len(current)):
            candidate = current[:index] + current[index + 1 :]
            if failure_signature(simulate(candidate)) == signature:
                current = candidate
                changed = True
                break
    return current


def run_campaign() -> Dict[str, Any]:
    cases = []
    for name, events, expected_outcome, expected_reason, expected_state in SCENARIOS:
        first = simulate(events)
        second = simulate(events)
        violations = []
        if first != second:
            violations.append("nondeterministic_replay")
        if (first["outcome"], first["reason"], first["state"]) != (expected_outcome, expected_reason, expected_state):
            violations.append("unexpected_terminal_result")
        signature = failure_signature(first)
        minimal_failure = minimize(events, signature) if expected_outcome == "failed" else None
        if minimal_failure is not None and failure_signature(simulate(minimal_failure)) != signature:
            violations.append("invalid_minimal_failure")
        if minimal_failure is not None and any(
            failure_signature(simulate(minimal_failure[:index] + minimal_failure[index + 1 :])) == signature
            for index in range(len(minimal_failure))
        ):
            violations.append("failure_not_one_minimal")
        cases.append({"name": name, "event_count": len(events), "outcome": first["outcome"], "reason": first["reason"], "state": first["state"], "minimal_failure_events": minimal_failure, "violations": violations, "passed": not violations})
    return {
        "suite": "xiaozhi_protocol_campaign",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(case["passed"] for case in cases) else "fail",
        "cases": cases,
        "evidence_boundary": "LiMa product-fork hello_ack/PCM WebSocket and MCP ordering model, informed by Xiaozhi upstream message families; PCM payload bytes are opaque and this does not prove audio fidelity, real audio, cloud service, ESP32 scheduling, Wi-Fi, or RF",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Xiaozhi deterministic protocol campaign")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_campaign()
    path = args.json_out or RESULTS / "protocol_campaign.json"
    if not path.is_absolute():
        path = HERE.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
