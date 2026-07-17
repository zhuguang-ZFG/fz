#!/usr/bin/env python3
"""Compare product protocol policy decisions with grblHAL responses."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FZ_ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).resolve().parent / "results"
sys.path.insert(0, str(FZ_ROOT))

from sim_common.find_sim import find_sim
from sim_common.grbl_tcp import GrblTcp, classify_responses
from sim_common.sim_session import start_protocol_session, stop_session

from run_protocol_decision_trace import run_trace
DEFAULT_LINES = [
    "G0 X1",
    "G1 X1 F100",
    "G2 X1 Y1 I1 J0",
    "G3 X1 Y1 I0 J1",
    "G10 L2 P1 X0",
    "G20",
    "G38.2 Z-1 F10",
    "G92 X0",
]


def classify_pair(product: Dict[str, Any], reference: str, error_code: Optional[str]) -> str:
    if reference in ("error", "alarm"):
        return "reference_rejected"
    if product["motion_g0_g3"]:
        return "product_motion_reference_ok"
    if reference == "ok":
        return "reference_ok_product_non_motion"
    return "reference_unknown"


def run_diff(
    lines: Sequence[str],
    grbl_root: Path,
    paper_running: bool = False,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if not find_sim():
        raise RuntimeError("grblHAL_sim not found")
    product = run_trace(lines, grbl_root, paper_running=paper_running)
    reference: List[Dict[str, Any]] = []
    for line in lines:
        session = None
        client: Optional[GrblTcp] = None
        try:
            session = start_protocol_session()
            client = GrblTcp(session.host, session.port, timeout=timeout)
            client.connect()
            responses = client.send_line(line, wait=min(timeout, 2.0))
            outcome, error_code = classify_responses(responses)
            reference.append(
                {"line": line, "responses": responses, "outcome": outcome, "error_code": error_code}
            )
        finally:
            if client is not None:
                client.close()
            stop_session(session)

    comparisons = []
    for item, product_item in zip(reference, product["lines"]):
        comparisons.append(
            {
                **item,
                "product": product_item,
                "classification": classify_pair(
                    product_item, item["outcome"], item["error_code"]
                ),
            }
        )
    return {
        "suite": "product_protocol_decision_diff",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "grbl_root": str(grbl_root),
        "product_trace": product,
        "comparisons": comparisons,
        "honesty": {
            "reference": "grblHAL response classifier",
            "product": "Grbl_Esp32 ProtocolDecisionCore policy only",
            "not_proven": ["full_product_parser_equivalence", "paper_mechanics", "Bluetooth_runtime"],
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="product protocol policy differential trace")
    parser.add_argument("--grbl-root", type=Path, default=Path(os.environ.get("GRBL_ROOT", "D:/Users/Grbl_Esp32")))
    parser.add_argument("--paper-running", action="store_true")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("lines", nargs="*")
    args = parser.parse_args(list(argv) if argv is not None else None)
    lines = args.lines or DEFAULT_LINES
    try:
        report = run_diff(lines, args.grbl_root.resolve(), args.paper_running, args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        report = {
            "suite": "product_protocol_decision_diff",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "fail",
            "error": str(exc),
        }
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "protocol_decision_diff.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
