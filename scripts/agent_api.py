#!/usr/bin/env python3
"""Transport-neutral Agent API for fz simulation tools and reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence


FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
LOCK_PATH = RESULTS / "agent_api.lock"
API_VERSION = 1
MAX_TIMEOUT_S = 1800
CASE_NAME = re.compile(r"^[A-Za-z0-9_.:-]+$")
PROFILES = ("auto", "quick", "standard", "deep", "firmware")
CLAIMS_FORBIDDEN = [
    "paper_path_verified",
    "bt_verified",
    "wifi_ota_verified",
    "product_flash_ok",
    "chip_qemu_app_ok",
    "xiaozhi_real_audio_verified",
    "xiaozhi_cloud_voice_verified",
]
REPORTS = {
    "gate": RESULTS / "agent_gate_last.json",
    "observe": RESULTS / "agent_observe_last.json",
    "triage": RESULTS / "triage_last.json",
    "protocol": FZ_ROOT / "protocol_sim" / "results" / "last_report.json",
    "hardware": FZ_ROOT / "hardware_sim" / "results" / "last_hw_report.json",
    "paper_plant": FZ_ROOT / "hardware_sim" / "results" / "paper_plant_campaign.json",
    "paper_interactions": FZ_ROOT / "hardware_sim" / "results" / "paper_plant_interactions.json",
    "paper_transients": FZ_ROOT / "hardware_sim" / "results" / "paper_plant_transients.json",
    "paper_contract": FZ_ROOT / "hardware_sim" / "results" / "paper_firmware_contract.json",
    "machine_pin_erc": FZ_ROOT / "hardware_sim" / "results" / "machine_pin_erc.json",
    "native": FZ_ROOT / "native_sim" / "results" / "last_report.json",
    "native_fuzz": FZ_ROOT / "native_sim" / "results" / "last_fuzz_report.json",
    "native_coverage": FZ_ROOT / "native_sim" / "results" / "coverage_summary.json",
    "protocol_decision_trace": FZ_ROOT / "native_sim" / "results" / "protocol_decision_trace.json",
    "protocol_decision_diff": FZ_ROOT / "native_sim" / "results" / "protocol_decision_diff.json",
    "protocol_scenarios": FZ_ROOT / "native_sim" / "results" / "protocol_scenarios.json",
    "protocol_scenario_schema": FZ_ROOT / "native_sim" / "results" / "protocol_scenario_schema.json",
    "qwen_gate": FZ_ROOT / "results" / "qwen_gate_last.json",
    "xiaozhi_protocol": FZ_ROOT / "xiaozhi_sim" / "results" / "protocol_campaign.json",
    "xiaozhi_firmware_contract": FZ_ROOT / "xiaozhi_sim" / "results" / "firmware_contract.json",
}
HARDWARE_BUILTINS = [
    "move_x_10",
    "move_xy_delta",
    "undefined_feed_G1",
    "settings_max_travel_roundtrip",
    "soft_limit_requires_homing",
    "plant_feed_hold",
    "override_realtime_100pct",
    "check_mode_toggle",
]
OPERATION_SCHEMAS = {
    "describe": {"type": "object", "additionalProperties": False},
    "list_cases": {
        "type": "object",
        "properties": {"domain": {"type": "string", "enum": ["protocol", "hardware", "all"]}},
        "additionalProperties": False,
    },
    "read_report": {
        "type": "object",
        "properties": {"name": {"type": "string", "enum": list(REPORTS)}},
        "required": ["name"],
        "additionalProperties": False,
    },
    "run_gate": {
        "type": "object",
        "properties": {
            "profile": {"type": "string", "enum": list(PROFILES)},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_paper_plant": {
        "type": "object",
        "properties": {
            "profiles": {"type": "array", "items": {"type": "string", "pattern": CASE_NAME.pattern}, "uniqueItems": True},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_paper_interactions": {
        "type": "object",
        "properties": {
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_paper_contract": {
        "type": "object",
        "properties": {
            "grbl_root": {"type": "string", "minLength": 1},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_machine_pin_erc": {
        "type": "object",
        "properties": {
            "grbl_root": {"type": "string", "minLength": 1},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_paper_transients": {
        "type": "object",
        "properties": {
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "list_qwen_profiles": {"type": "object", "additionalProperties": False},
    "run_qwen_gate": {
        "type": "object",
        "properties": {
            "profile": {
                "type": "string",
                "enum": ["firmware_contract", "motion_contract", "drawing_e2e", "voice_contract", "standard"],
            },
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_xiaozhi_protocol": {
        "type": "object",
        "properties": {"timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S}},
        "additionalProperties": False,
    },
    "run_xiaozhi_contract": {
        "type": "object",
        "properties": {"timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S}},
        "additionalProperties": False,
    },
    "list_scenarios": {"type": "object", "additionalProperties": False},
    "run_scenarios": {
        "type": "object",
        "properties": {
            "names": {"type": "array", "items": {"type": "string", "pattern": CASE_NAME.pattern}, "uniqueItems": True},
            "shrink": {"type": "boolean"},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_product_trace": {
        "type": "object",
        "properties": {
            "paper_running": {"type": "boolean"},
            "modal_motion_active": {"type": "boolean"},
            "stateful_modal": {"type": "boolean"},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "run_differential": {
        "type": "object",
        "properties": {
            "paper_running": {"type": "boolean"},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "additionalProperties": False,
    },
    "rerun_cases": {
        "type": "object",
        "properties": {
            "protocol": {"type": "array", "items": {"type": "string", "pattern": CASE_NAME.pattern}, "uniqueItems": True},
            "hardware": {"type": "array", "items": {"type": "string", "pattern": CASE_NAME.pattern}, "uniqueItems": True},
            "timeout_s": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_TIMEOUT_S},
        },
        "anyOf": [{"required": ["protocol"]}, {"required": ["hardware"]}],
        "additionalProperties": False,
    },
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _configure_console_encoding() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


_configure_console_encoding()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(request_id: str, operation: str, ok: bool, **fields: Any) -> Dict[str, Any]:
    return {
        "api": "fz_agent_api",
        "version": API_VERSION,
        "request_id": request_id,
        "operation": operation,
        "ok": ok,
        "timestamp": _utc_now(),
        "claims_forbidden": CLAIMS_FORBIDDEN,
        **fields,
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ApiError("report_not_found", f"report does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError("report_invalid", f"cannot read report: {path}", {"reason": str(exc)}) from exc


def _validated_timeout(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError("invalid_request", "timeout_s must be a number")
    timeout = float(value)
    if timeout <= 0 or timeout > MAX_TIMEOUT_S:
        raise ApiError("invalid_request", f"timeout_s must be within 0..{MAX_TIMEOUT_S}")
    return timeout



def _validated_bool(value: Any, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ApiError("invalid_request", f"{field} must be a boolean")
    return value
def _validated_names(value: Any, field: str, allowed: Sequence[str]) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ApiError("invalid_request", f"{field} must be a list of case names")
    names = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    invalid = [name for name in names if not CASE_NAME.fullmatch(name)]
    unknown = [name for name in names if name not in allowed]
    if invalid or unknown:
        raise ApiError(
            "unknown_case",
            f"invalid or unknown {field}",
            {"invalid": invalid, "unknown": unknown, "allowed": list(allowed)},
        )
    return names


def _protocol_cases() -> List[Dict[str, str]]:
    cases: List[Dict[str, str]] = []
    root = FZ_ROOT / "protocol_sim" / "cases"
    for kind_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        for path in sorted(kind_dir.iterdir()):
            if path.suffix.lower() not in (".json", ".nc"):
                continue
            cases.append({"kind": kind_dir.name, "name": path.stem, "path": path.relative_to(FZ_ROOT).as_posix()})
    return cases


def _hardware_cases() -> List[Dict[str, str]]:
    cases = [{"kind": "builtin", "name": name, "path": "hardware_sim/run_hw_sim.py"} for name in HARDWARE_BUILTINS]
    for path in sorted((FZ_ROOT / "hardware_sim" / "cases").glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            name = path.stem
        else:
            name = str(raw.get("id") or path.stem) if isinstance(raw, dict) else path.stem
        cases.append({"kind": "json", "name": name, "path": path.relative_to(FZ_ROOT).as_posix()})
    return cases


def _protocol_scenarios() -> List[Dict[str, str]]:
    cases: List[Dict[str, str]] = []
    for path in sorted((FZ_ROOT / "native_sim" / "scenarios").glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict) and isinstance(raw.get("name"), str):
            cases.append({"name": raw["name"], "file": path.stem, "path": path.relative_to(FZ_ROOT).as_posix()})
    return cases
def _process_alive(pid: Any) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _valid_pid(pid: Any) -> bool:
    return not isinstance(pid, bool) and isinstance(pid, int) and pid > 0


def _existing_lock() -> Dict[str, Any]:
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _open_execution_lock(payload: str) -> int:
    try:
        return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as first_error:
        details = _existing_lock()
        pid = details.get("pid")
        if details and _valid_pid(pid) and not _process_alive(pid):
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                pass
            try:
                return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                details = _existing_lock()
        raise ApiError("busy", "another simulation request is running", details) from first_error


@contextmanager
def _execution_lock(request_id: str, operation: str) -> Iterator[None]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"request_id": request_id, "operation": operation, "pid": os.getpid(), "started_at": _utc_now()})
    descriptor = _open_execution_lock(payload)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload + "\n")
        yield
    finally:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def _run(command: List[str], timeout_s: float) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=str(FZ_ROOT),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise ApiError(
            "timeout",
            f"operation exceeded {timeout_s}s",
            {"stdout_tail": (exc.stdout or "")[-4000:], "stderr_tail": (exc.stderr or "")[-4000:]},
        ) from exc
    return {
        "exit_code": result.returncode,
        "duration_s": round(time.monotonic() - started, 2),
        "stdout_tail": result.stdout[-8000:],
        "stderr_tail": result.stderr[-8000:],
    }


QWEN_PROFILES = ("firmware_contract", "motion_contract", "drawing_e2e", "voice_contract", "standard")

def describe() -> Dict[str, Any]:
    return {
        "operations": OPERATION_SCHEMAS,
        "reports": {name: path.relative_to(FZ_ROOT).as_posix() for name, path in REPORTS.items()},
        "mcp_mapping": {"tools": ["run_gate", "rerun_cases", "run_product_trace", "run_differential", "run_scenarios", "run_paper_plant", "run_paper_interactions", "run_paper_transients", "run_paper_contract", "run_machine_pin_erc", "run_qwen_gate", "run_xiaozhi_protocol", "run_xiaozhi_contract"], "resources": ["describe", "list_cases", "list_scenarios", "list_qwen_profiles", "read_report"]},
    }


def dispatch(request: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(request, dict):
        raise ApiError("invalid_request", "request must be a JSON object")
    operation = request.get("operation")
    if not isinstance(operation, str) or not operation:
        raise ApiError("invalid_request", "operation is required")
    request_id = str(request.get("request_id") or uuid.uuid4())
    params = request.get("params") or {}
    if not isinstance(params, dict):
        raise ApiError("invalid_request", "params must be an object")

    if operation == "describe":
        return _envelope(request_id, operation, True, result=describe())
    if operation == "list_cases":
        domain = params.get("domain", "all")
        if domain not in ("protocol", "hardware", "all"):
            raise ApiError("invalid_request", "domain must be protocol, hardware, or all")
        result: Dict[str, Any] = {}
        if domain in ("protocol", "all"):
            result["protocol"] = _protocol_cases()
        if domain in ("hardware", "all"):
            result["hardware"] = _hardware_cases()
        return _envelope(request_id, operation, True, result=result)
    if operation == "list_qwen_profiles":
        return _envelope(request_id, operation, True, result={"profiles": list(QWEN_PROFILES), "qwen_root_env": "QWEN_ROOT"})
    if operation == "list_scenarios":
        return _envelope(request_id, operation, True, result=_protocol_scenarios())
    if operation == "read_report":
        name = params.get("name")
        if name not in REPORTS:
            raise ApiError("invalid_request", "unknown report name", {"allowed": list(REPORTS)})
        path = REPORTS[str(name)]
        return _envelope(
            request_id,
            operation,
            True,
            result={"name": name, "path": path.relative_to(FZ_ROOT).as_posix(), "content": _load_json(path)},
        )
    if operation == "run_paper_plant":
        profiles = _validated_names(
            params.get("profiles"),
            "profiles",
            ["nominal", "slip_40pct", "jam", "no_paper", "sensor_stuck_inactive", "sensor_stuck_active", "sensor_bounce", "motor_reverse", "slip_plus_bounce", "slip_plus_jam"],
        )
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "paper_plant_requests" / f"{report_key}.json"
        command = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_paper_plant_campaign.py"),
            "--json-out",
            str(request_report),
        ]
        for profile in profiles:
            command.extend(["--only", profile])
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_paper_interactions":
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "paper_plant_requests" / f"{report_key}-interactions.json"
        command = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_paper_plant_interactions.py"),
            "--json-out",
            str(request_report),
        ]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_paper_contract":
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        grbl_root = Path(str(params.get("grbl_root") or os.environ.get("GRBL_ROOT") or "D:/Users/Grbl_Esp32")).resolve()
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "paper_plant_requests" / f"{report_key}-contract.json"
        command = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_paper_firmware_contract.py"),
            "--grbl-root",
            str(grbl_root),
            "--json-out",
            str(request_report),
        ]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_machine_pin_erc":
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        grbl_root = Path(str(params.get("grbl_root") or os.environ.get("GRBL_ROOT") or "D:/Users/Grbl_Esp32")).resolve()
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "paper_plant_requests" / f"{report_key}-machine-pin-erc.json"
        command = [sys.executable, str(FZ_ROOT / "hardware_sim" / "run_machine_pin_erc.py"), "--grbl-root", str(grbl_root), "--json-out", str(request_report)]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_paper_transients":
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "paper_plant_requests" / f"{report_key}-transients.json"
        command = [
            sys.executable,
            str(FZ_ROOT / "hardware_sim" / "run_paper_transient_campaign.py"),
            "--json-out",
            str(request_report),
        ]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_gate":
        profile = params.get("profile", "standard")
        if profile not in PROFILES:
            raise ApiError("invalid_request", "unknown gate profile", {"allowed": list(PROFILES)})
        timeout_s = _validated_timeout(params.get("timeout_s", 600))
        command = [sys.executable, str(FZ_ROOT / "scripts" / "agent_gate.py"), "--profile", str(profile)]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(REPORTS["gate"])
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_qwen_gate":
        profile = params.get("profile", "standard")
        if profile not in QWEN_PROFILES:
            raise ApiError("invalid_request", "unknown QWEN profile", {"allowed": list(QWEN_PROFILES)})
        timeout_s = _validated_timeout(params.get("timeout_s", 600))
        qwen_root = Path(os.environ.get("QWEN_ROOT", "D:/QWEN3.0")).resolve()
        command = [
            sys.executable,
            str(FZ_ROOT / "scripts" / "qwen_evidence_adapter.py"),
            "--profile",
            str(profile),
            "--qwen-root",
            str(qwen_root),
            "--timeout",
            str(timeout_s),
            "--request-id",
            request_id,
        ]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s + 30)
        report = _load_json(REPORTS["qwen_gate"])
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_xiaozhi_protocol":
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "xiaozhi_requests" / f"{report_key}.json"
        command = [sys.executable, str(FZ_ROOT / "xiaozhi_sim" / "run_protocol_campaign.py"), "--json-out", str(request_report)]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_xiaozhi_contract":
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        qwen_root = Path(os.environ.get("QWEN_ROOT", "D:/QWEN3.0")).resolve()
        report_key = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        request_report = RESULTS / "xiaozhi_requests" / f"{report_key}-contract.json"
        command = [sys.executable, str(FZ_ROOT / "xiaozhi_sim" / "run_firmware_contract.py"), "--qwen-root", str(qwen_root), "--json-out", str(request_report)]
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(request_report)
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "run_scenarios":
        available = _protocol_scenarios()
        by_name = {item["name"]: item["file"] for item in available}
        names = _validated_names(params.get("names"), "names", list(by_name))
        shrink = _validated_bool(params.get("shrink"), "shrink", default=True)
        timeout_s = _validated_timeout(params.get("timeout_s", 180))
        command = [sys.executable, str(FZ_ROOT / "native_sim" / "run_protocol_scenarios.py")]
        for name in names:
            command.extend(["--only", by_name[name]])
        if not shrink:
            command.append("--no-shrink")
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(REPORTS["protocol_scenarios"])
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation in ("run_product_trace", "run_differential"):
        timeout_s = _validated_timeout(params.get("timeout_s", 120))
        script = "run_protocol_decision_trace.py" if operation == "run_product_trace" else "run_protocol_decision_diff.py"
        report_name = "protocol_decision_trace" if operation == "run_product_trace" else "protocol_decision_diff"
        command = [sys.executable, str(FZ_ROOT / "native_sim" / script)]
        paper_running = _validated_bool(params.get("paper_running"), "paper_running")
        modal_motion_active = _validated_bool(params.get("modal_motion_active"), "modal_motion_active")
        stateful_modal = _validated_bool(params.get("stateful_modal"), "stateful_modal")
        if operation == "run_differential" and (modal_motion_active or stateful_modal):
            raise ApiError("invalid_request", "modal options are only supported by run_product_trace")
        if paper_running:
            command.append("--paper-running")
        if operation == "run_product_trace" and modal_motion_active:
            command.append("--modal-motion-active")
        if operation == "run_product_trace" and stateful_modal:
            command.append("--stateful-modal")
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        report = _load_json(REPORTS[report_name])
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=report)
    if operation == "rerun_cases":
        protocol_cases = _protocol_cases()
        hardware_cases = _hardware_cases()
        protocol = _validated_names(params.get("protocol"), "protocol", [case["name"] for case in protocol_cases])
        hardware = _validated_names(params.get("hardware"), "hardware", [case["name"] for case in hardware_cases])
        if not protocol and not hardware:
            raise ApiError("invalid_request", "at least one protocol or hardware case is required")
        timeout_s = _validated_timeout(params.get("timeout_s", 300))
        command = [sys.executable, str(FZ_ROOT / "scripts" / "sim_rerun.py")]
        if protocol:
            command.extend(["--protocol", ",".join(protocol)])
        if hardware:
            command.extend(["--hardware", ",".join(hardware)])
        with _execution_lock(request_id, operation):
            execution = _run(command, timeout_s)
        result = {
            "protocol": _load_json(REPORTS["protocol"]) if protocol else None,
            "hardware": _load_json(REPORTS["hardware"]) if hardware else None,
        }
        return _envelope(request_id, operation, execution["exit_code"] == 0, execution=execution, result=result)
    raise ApiError("unknown_operation", f"unsupported operation: {operation}", {"allowed": list(describe()["operations"])})


def handle(request: Any) -> Dict[str, Any]:
    request_id = str(request.get("request_id") or uuid.uuid4()) if isinstance(request, dict) else str(uuid.uuid4())
    operation = str(request.get("operation") or "unknown") if isinstance(request, dict) else "unknown"
    try:
        return dispatch(request)
    except ApiError as exc:
        return _envelope(
            request_id,
            operation,
            False,
            error={"code": exc.code, "message": exc.message, "details": exc.details},
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="fz transport-neutral Agent API")
    parser.add_argument("--request", help="JSON request; default reads one object from stdin")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        raw = args.request if args.request is not None else sys.stdin.read()
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        response = handle({"operation": "unknown", "params": {}})
        response["error"] = {"code": "invalid_json", "message": str(exc), "details": {}}
        response["ok"] = False
    else:
        response = handle(request)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
