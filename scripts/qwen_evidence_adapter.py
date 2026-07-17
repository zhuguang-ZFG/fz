#!/usr/bin/env python3
"""Run whitelisted QWEN/Xiaozhi pytest evidence profiles from fz."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = FZ_ROOT / "results"
PROFILES = {
    "firmware_contract": ("tests/test_firmware_hardware_gate.py",),
    "motion_contract": (
        "tests/test_motion.py",
        "tests/test_device_motion.py",
        "tests/test_device_gateway_motion_contract.py",
        "tests/test_device_gateway_path_pipeline.py",
    ),
    "drawing_e2e": (
        "tests/test_drawing_pipeline.py",
        "tests/test_drawing_pipeline_e2e.py",
    ),
    "voice_contract": (
        "tests/test_device_app_voice.py",
        "tests/test_device_app_voice_ws.py",
        "tests/test_device_voice_providers.py",
        "tests/test_device_voice_streaming.py",
        "tests/test_voice_e2e_probe.py",
    ),
}
PROFILES["standard"] = tuple(
    dict.fromkeys(path for name in ("firmware_contract", "motion_contract", "drawing_e2e", "voice_contract") for path in PROFILES[name])
)
SUMMARY_PATTERN = re.compile(r"(?P<count>\d+) (?P<kind>passed|failed|skipped|error|errors|xfailed|xpassed)")


def find_python(qwen_root: Path) -> Path:
    candidates = [
        qwen_root / ".venv310" / "Scripts" / "python.exe",
        qwen_root / ".venv" / "Scripts" / "python.exe",
    ]
    return next((path for path in candidates if path.is_file()), Path(sys.executable))


def parse_summary(output: str) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for match in SUMMARY_PATTERN.finditer(output):
        kind = match.group("kind")
        if kind == "errors":
            kind = "error"
        summary[kind] = summary.get(kind, 0) + int(match.group("count"))
    return summary


def run_profile(profile: str, qwen_root: Path, request_id: str, timeout_s: float) -> Dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"unknown QWEN profile: {profile}; allowed: {list(PROFILES)}")
    if not (qwen_root / "AGENTS.md").is_file():
        raise RuntimeError(f"invalid QWEN root: {qwen_root}")
    python = find_python(qwen_root)
    temp_root = RESULTS / "qwen_pytest_tmp" / request_id
    temp_root.mkdir(parents=True, exist_ok=True)
    command = [
        str(python),
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        *PROFILES[profile],
        "-q",
        "--tb=short",
        "--basetemp",
        str(temp_root),
    ]
    started = time.monotonic()
    try:
        run = subprocess.run(
            command,
            cwd=str(qwen_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        output = run.stdout + ("\n" + run.stderr if run.stderr else "")
        return {
            "suite": "qwen_evidence_gate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "profile": profile,
            "status": "pass" if run.returncode == 0 else "fail",
            "exit_code": run.returncode,
            "duration_s": round(time.monotonic() - started, 2),
            "qwen_root": str(qwen_root),
            "python": str(python),
            "targets": list(PROFILES[profile]),
            "summary": parse_summary(output),
            "stdout_tail": run.stdout[-12000:],
            "stderr_tail": run.stderr[-8000:],
            "evidence_boundary": (
                "QWEN pytest/FakeDevice/voice contracts; no real microphone, speaker, Opus hardware, cloud credentials, or RF evidence; "
                "motion correctness still requires fz host SIL and paper/BT require HIL"
            ),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "suite": "qwen_evidence_gate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "profile": profile,
            "status": "fail",
            "error": "timeout",
            "duration_s": round(time.monotonic() - started, 2),
            "stdout_tail": (exc.stdout or "")[-8000:],
            "stderr_tail": (exc.stderr or "")[-8000:],
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="run whitelisted QWEN evidence profile")
    parser.add_argument("--profile", choices=list(PROFILES), default="standard")
    parser.add_argument("--qwen-root", type=Path, default=Path(os.environ.get("QWEN_ROOT", "D:/QWEN3.0")))
    parser.add_argument("--request-id", default=str(uuid.uuid4()))
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.timeout <= 0 or args.timeout > 1800:
        parser.error("--timeout must be within 0..1800")
    try:
        report = run_profile(args.profile, args.qwen_root.resolve(), args.request_id, args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        report = {
            "suite": "qwen_evidence_gate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": args.request_id,
            "profile": args.profile,
            "status": "fail",
            "error": str(exc),
        }
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "qwen_gate_last.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
