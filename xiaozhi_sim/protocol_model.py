#!/usr/bin/env python3
"""Deterministic Xiaozhi WebSocket protocol state model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

PRODUCT_PROTOCOL = "lima-device-v1"
PRODUCT_CLIENT_HELLO_TYPE = "hello"
PRODUCT_SERVER_HELLO_TYPE = "hello_ack"
PRODUCT_AUDIO = {"format": "pcm", "sample_rate": 16000, "channels": 1, "sample_width": 2, "frame_duration": 60}
PRODUCT_CAPABILITIES = {"audio", "run_path", "device_info", "self_check"}
PRODUCT_INCOMING_TYPES = {"hello_ack", "voice_status", "audio_reply", "tts", "stt", "llm", "mcp", "motion_task", "system", "alert", "custom"}


@dataclass
class XiaozhiProtocolModel:
    state: str = "disconnected"
    session_id: Optional[str] = None
    outcome: str = "running"
    reason: str = ""
    pending_mcp_ids: set[int] = field(default_factory=set)
    trace: List[Dict[str, Any]] = field(default_factory=list)

    def apply(self, event: Dict[str, Any]) -> None:
        if self.outcome != "running":
            return
        kind = event.get("kind")
        before = self.state
        handler = getattr(self, f"_on_{kind}", None) if isinstance(kind, str) else None
        if handler is None:
            self._fail("unknown_event")
        else:
            handler(event)
        self.trace.append({"kind": kind, "before": before, "after": self.state, "outcome": self.outcome, "reason": self.reason})

    def _fail(self, reason: str) -> None:
        self.outcome = "failed"
        self.reason = reason
        self.state = "disconnected"
        self.pending_mcp_ids.clear()

    def _require_session(self, event: Dict[str, Any]) -> bool:
        if event.get("session_id") != self.session_id:
            self._fail("session_mismatch")
            return False
        return True

    def _on_connect(self, _event: Dict[str, Any]) -> None:
        if self.state != "disconnected":
            self._fail("duplicate_connect")
            return
        self.state = "awaiting_hello"

    def _on_hello_ack(self, event: Dict[str, Any]) -> None:
        if self.state != "awaiting_hello":
            self._fail("invalid_hello")
            return
        session_id = event.get("device_id")
        self.session_id = session_id if isinstance(session_id, str) and session_id else None
        self.state = "idle"

    def _on_hello_timeout(self, _event: Dict[str, Any]) -> None:
        self._fail("hello_timeout" if self.state == "awaiting_hello" else "unexpected_timeout")

    def _on_listen_start(self, event: Dict[str, Any]) -> None:
        if not self._require_session(event):
            return
        if self.state not in {"idle", "speaking"} or event.get("mode") not in {"auto", "manual", "realtime"}:
            self._fail("invalid_listen_start")
            return
        self.state = "listening"

    def _on_listen_stop(self, event: Dict[str, Any]) -> None:
        if self._require_session(event) and self.state == "listening":
            self.state = "idle"
        elif self.outcome == "running":
            self._fail("invalid_listen_stop")

    def _on_uplink_audio(self, event: Dict[str, Any]) -> None:
        if self._require_session(event) and self.state != "listening":
            self._fail("audio_outside_listening")

    def _on_tts_start(self, event: Dict[str, Any]) -> None:
        if self._require_session(event) and self.state in {"idle", "listening"}:
            self.state = "speaking"
        elif self.outcome == "running":
            self._fail("invalid_tts_start")

    def _on_downlink_audio(self, event: Dict[str, Any]) -> None:
        if self._require_session(event) and self.state != "speaking":
            self._fail("audio_outside_speaking")

    def _on_tts_stop(self, event: Dict[str, Any]) -> None:
        if self._require_session(event) and self.state == "speaking":
            self.state = "idle"
        elif self.outcome == "running":
            self._fail("invalid_tts_stop")

    def _on_abort(self, event: Dict[str, Any]) -> None:
        if self._require_session(event) and self.state == "speaking":
            self.state = "listening"
        elif self.outcome == "running":
            self._fail("invalid_abort")

    def _on_disconnect(self, _event: Dict[str, Any]) -> None:
        self.state = "disconnected"
        self.session_id = None
        self.pending_mcp_ids.clear()

    def _on_mcp_request(self, event: Dict[str, Any]) -> None:
        request_id = event.get("id")
        method = event.get("method")
        if event.get("jsonrpc") != "2.0" or self.state not in {"idle", "listening", "speaking"} or not isinstance(request_id, int) or isinstance(request_id, bool):
            self._fail("invalid_mcp_request")
        elif method not in {"initialize", "tools/list", "tools/call"} or request_id in self.pending_mcp_ids:
            self._fail("invalid_mcp_request")
        else:
            self.pending_mcp_ids.add(request_id)

    def _on_mcp_response(self, event: Dict[str, Any]) -> None:
        request_id = event.get("id")
        has_result = "result" in event
        has_error = "error" in event
        if event.get("jsonrpc") != "2.0" or request_id not in self.pending_mcp_ids or has_result == has_error:
            self._fail("invalid_mcp_response")
            return
        self.pending_mcp_ids.remove(request_id)

    def report(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "state": self.state,
            "session_id": self.session_id,
            "pending_mcp_ids": sorted(self.pending_mcp_ids),
            "trace": self.trace,
        }


def simulate(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    model = XiaozhiProtocolModel()
    for event in events:
        if not isinstance(event, dict):
            model._fail("invalid_event")
            break
        model.apply(event)
    return model.report()
