#!/usr/bin/env python3
"""Detect drift between the LiMa Xiaozhi firmware fork and the PC model."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from protocol_model import PRODUCT_AUDIO, PRODUCT_CAPABILITIES, PRODUCT_CLIENT_HELLO_TYPE, PRODUCT_INCOMING_TYPES, PRODUCT_PROTOCOL, PRODUCT_SERVER_HELLO_TYPE

HERE = Path(__file__).resolve().parent
FZ_ROOT = HERE.parent
RESULTS = HERE / "results"
DEFAULT_CONTRACT = HERE / "firmware_contract.json"


def one(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing source anchor: {label}")
    return match.group(1)


def extract_firmware(firmware_root: Path) -> Dict[str, Any]:
    websocket = (firmware_root / "main/protocols/websocket_protocol.cc").read_text(encoding="utf-8", errors="replace")
    application = (firmware_root / "main/application.cc").read_text(encoding="utf-8", errors="replace")
    return {
        "protocol": one(r'#define\s+LIMA_PROTOCOL_VERSION\s+"([^"]+)"', websocket, "protocol"),
        "client_hello_type": one(r'AddStringToObject\(root,\s*"type",\s*"([^"]+)"\)', websocket, "client hello"),
        "server_hello_type": one(r'strcmp\(type->valuestring,\s*"([^"]+)"\)\s*==\s*0\)\s*\{\s*ParseServerHello', websocket, "server hello"),
        "audio": {
            "format": one(r'AddStringToObject\(audio_params,\s*"format",\s*"([^"]+)"\)', websocket, "audio format"),
            "sample_rate": int(one(r'AddNumberToObject\(audio_params,\s*"sample_rate",\s*(\d+)\)', websocket, "sample rate")),
            "channels": int(one(r'AddNumberToObject\(audio_params,\s*"channels",\s*(\d+)\)', websocket, "channels")),
            "sample_width": int(one(r'AddNumberToObject\(audio_params,\s*"sample_width",\s*(\d+)\)', websocket, "sample width")),
            "frame_duration": int(one(r'server_frame_duration_\s*=\s*(\d+)\s*;', websocket, "frame duration")),
        },
        "capabilities": sorted(set(re.findall(r'AddItemToArray\(capabilities,\s*cJSON_CreateString\("([^"]+)"\)\)', websocket))),
        "incoming_types": sorted(set(re.findall(r'strcmp\(type->valuestring,\s*"([^"]+)"\)\s*==\s*0', websocket + "\n" + application))),
    }


def load_contract(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"protocol", "client_hello_type", "server_hello_type", "audio", "capabilities", "incoming_types"}
    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or not isinstance(data.get("firmware_root"), str)
        or not data.get("firmware_root")
        or not isinstance(data.get("expected"), dict)
        or not required.issubset(data["expected"])
    ):
        raise ValueError("Xiaozhi firmware contract version must be 1 with expected object")
    return data


def compare(prefix: str, expected: Any, actual: Any, violations: List[Dict[str, Any]]) -> None:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        for key, value in expected.items():
            compare(f"{prefix}.{key}" if prefix else str(key), value, actual.get(key), violations)
    elif isinstance(expected, list) and isinstance(actual, list):
        if sorted(expected) != sorted(actual):
            violations.append({"kind": "contract_drift", "field": prefix, "expected": expected, "actual": actual})
    elif expected != actual:
        violations.append({"kind": "contract_drift", "field": prefix, "expected": expected, "actual": actual})


def validate_contract(contract: Mapping[str, Any], qwen_root: Path) -> Dict[str, Any]:
    root = qwen_root.resolve()
    firmware_root = (root / str(contract.get("firmware_root", ""))).resolve()
    if firmware_root != root and root not in firmware_root.parents:
        raise ValueError(f"firmware_root escapes QWEN_ROOT: {contract.get('firmware_root')}")
    observed = extract_firmware(firmware_root)
    model = {
        "protocol": PRODUCT_PROTOCOL,
        "client_hello_type": PRODUCT_CLIENT_HELLO_TYPE,
        "server_hello_type": PRODUCT_SERVER_HELLO_TYPE,
        "audio": PRODUCT_AUDIO,
        "capabilities": sorted(PRODUCT_CAPABILITIES),
        "incoming_types": sorted(PRODUCT_INCOMING_TYPES),
    }
    violations: List[Dict[str, Any]] = []
    compare("firmware", contract["expected"], observed, violations)
    compare("model.protocol", contract["expected"]["protocol"], model["protocol"], violations)
    compare("model.client_hello_type", contract["expected"]["client_hello_type"], model["client_hello_type"], violations)
    compare("model.server_hello_type", contract["expected"]["server_hello_type"], model["server_hello_type"], violations)
    compare("model.audio", contract["expected"]["audio"], model["audio"], violations)
    compare("model.capabilities", contract["expected"]["capabilities"], model["capabilities"], violations)
    compare("model.incoming_types", contract["expected"]["incoming_types"], model["incoming_types"], violations)
    return {
        "suite": "xiaozhi_firmware_model_contract",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not violations else "fail",
        "qwen_root": str(qwen_root.resolve()),
        "firmware_root": str(firmware_root.resolve()),
        "observed_firmware": observed,
        "observed_model": model,
        "violations": violations,
        "evidence_boundary": contract.get("evidence_boundary"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="LiMa Xiaozhi firmware/model drift contract")
    parser.add_argument("--qwen-root", type=Path, default=Path("D:/QWEN3.0"))
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = validate_contract(load_contract(args.contract), args.qwen_root.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"suite": "xiaozhi_firmware_model_contract", "timestamp": datetime.now(timezone.utc).isoformat(), "status": "fail", "violations": [{"kind": "invalid_contract", "detail": str(exc)}]}
    path = args.json_out or RESULTS / "firmware_contract.json"
    if not path.is_absolute():
        path = FZ_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
