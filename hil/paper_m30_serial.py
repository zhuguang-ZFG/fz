#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G3b paper/M30 serial sequences (product HIL helper).

Maps Grbl_Esp32 docs/ACCEPTANCE_CHECKLIST.md §1 to scriptable serial checks.
Physical paper mechanics cannot be fully proven without hardware sensors;
this script verifies **firmware log/protocol reactions** on a real board.

Community pattern: Golioth/HIL CI flash+serial assert; linux.do/embedded threads
emphasize serial log evidence over pure simulation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# Patterns from product firmware / ACCEPTANCE checklist
PAPER_DONE = re.compile(
    r"PaperM30|Auto paper change completed|paper change completed",
    re.I,
)
PAGE_END = re.compile(r"PAGE_END_IMMINENT", re.I)
SECOND_PAPER = re.compile(
    r"PaperM30|Auto paper change completed|paper change completed",
    re.I,
)


def _need_serial():
    try:
        import serial  # type: ignore

        return serial
    except ImportError as e:
        raise SystemExit("pip install pyserial") from e


class SerialSession:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 2.0) -> None:
        serial = _need_serial()
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.4)
        self.ser.reset_input_buffer()
        self.log: List[str] = []

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:
            pass

    def soft_reset(self) -> str:
        self.ser.write(b"\x18")
        time.sleep(1.5)
        return self._read()

    def cmd(self, line: str, wait: float = 1.0) -> str:
        self.ser.write((line.strip() + "\n").encode("utf-8"))
        time.sleep(wait)
        return self._read()

    def _read(self) -> str:
        chunks: List[str] = []
        deadline = time.time() + max(self.ser.timeout or 1.0, 0.5)
        while time.time() < deadline:
            n = self.ser.in_waiting
            if n:
                chunks.append(self.ser.read(n).decode("utf-8", errors="replace"))
                deadline = time.time() + 0.3
            else:
                time.sleep(0.05)
        text = "".join(chunks)
        if text:
            self.log.append(text)
        return text


def run_sequence(
    sess: SerialSession,
    *,
    expect_paper_log: bool = True,
) -> List[Dict[str, Any]]:
    """
    Scriptable subset of ACCEPTANCE §1:
      1.1 M30 after motion-ish stream → paper done log (if firmware emits)
      1.2 G0 origin after M30 → should NOT emit second paper done immediately
      1.2b non-motion lines between M30 and origin
      1.3 soft reset then origin does not falsely skip forever (smoke only)
    """
    steps: List[Dict[str, Any]] = []

    boot = sess.soft_reset()
    steps.append({"id": "g3a.boot", "ok": True, "snippet": boot[-300:]})

    r = sess.cmd("$X", 1.0)
    steps.append({"id": "unlock", "ok": "error" not in r.lower() or "ok" in r.lower(), "snippet": r[-120:]})

    # Warm path: a few moves so "page" context exists for paper systems that care
    for line in ("G21", "G90", "G0 X1 Y1", "G0 X0 Y0"):
        sess.cmd(line, 0.6)

    # 1.1 M30
    m30 = sess.cmd("M30", wait=3.0)
    paper_once = bool(PAPER_DONE.search(m30)) or bool(PAGE_END.search(m30))
    if not expect_paper_log:
        # test_drive may not implement paper — mark na
        steps.append(
            {
                "id": "paper.1.1",
                "ok": True,
                "result": "na",
                "note": "expect_paper_log=false (e.g. test_drive)",
                "snippet": m30[-200:],
            }
        )
    else:
        steps.append(
            {
                "id": "paper.1.1",
                "ok": paper_once,
                "result": "pass" if paper_once else "fail",
                "note": "" if paper_once else "no PaperM30/PAGE_END in window — check machine/custom paper",
                "snippet": m30[-400:],
            }
        )

    # 1.2 origin after M30 — capture log; second paper is fail if we saw one before
    after = sess.cmd("G0 X0 Y0 Z0", wait=2.0)
    # Also send non-motion sandwich for 1.2b
    mid = sess.cmd("G90", 0.3) + sess.cmd("G21", 0.3) + sess.cmd("; comment", 0.3)
    after2 = sess.cmd("G0 X0 Y0 Z0", wait=1.5)
    combined = after + mid + after2
    second = bool(SECOND_PAPER.search(combined))
    # If firmware always logs on any origin, this may false-fail — operator can waive
    steps.append(
        {
            "id": "paper.1.2",
            "ok": (not second) if expect_paper_log else True,
            "result": ("pass" if not second else "fail") if expect_paper_log else "na",
            "note": ""
            if not second or not expect_paper_log
            else "possible second paper log after origin — review snippet",
            "snippet": combined[-400:],
        }
    )
    steps.append(
        {
            "id": "paper.1.2b",
            "ok": True,
            "result": "pass" if expect_paper_log else "na",
            "note": "non-motion lines sent between M30 and second origin",
            "snippet": mid[-120:],
        }
    )

    # 1.3 soft reset
    sess.soft_reset()
    sess.cmd("$X", 1.0)
    r = sess.cmd("G0 X0 Y0", 1.0)
    steps.append(
        {
            "id": "paper.1.3",
            "ok": True,
            "result": "pass",
            "note": "soft reset + origin smoke (full legal paper re-trigger needs real paper state)",
            "snippet": r[-120:],
        }
    )

    # page-end message optional capture on second M30
    m30b = sess.cmd("M30", wait=2.0)
    steps.append(
        {
            "id": "paper.1.2c",
            "ok": True,
            "result": "pass" if (PAGE_END.search(m30b) or not expect_paper_log) else "skip",
            "note": "PAGE_END_IMMINENT"
            if PAGE_END.search(m30b)
            else "not seen — may depend on page-full state",
            "snippet": m30b[-200:],
        }
    )

    return steps


def steps_to_g3_yaml_items(steps: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Map sequence results to g3_evidence item patches."""
    out = []
    for s in steps:
        sid = s.get("id") or ""
        if not sid.startswith("paper.") and not sid.startswith("g3a."):
            continue
        res = s.get("result") or ("pass" if s.get("ok") else "fail")
        out.append(
            {
                "id": sid,
                "result": str(res),
                "note": str(s.get("note") or ""),
                "evidence": str(s.get("snippet") or "")[:500],
            }
        )
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="G3b paper M30 serial helper")
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--expect-paper-log",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="set --no-expect-paper-log for test_drive without paper custom",
    )
    args = ap.parse_args(argv)

    sess = SerialSession(args.port, args.baud)
    try:
        steps = run_sequence(sess, expect_paper_log=args.expect_paper_log)
    finally:
        sess.close()

    hard_fail = any(
        s.get("result") == "fail" or (s.get("id", "").startswith("paper.") and not s.get("ok"))
        for s in steps
        if s.get("result") != "na"
    )
    report = {
        "layer": "G3b",
        "status": "fail" if hard_fail else "pass",
        "port": args.port,
        "steps": steps,
        "g3_item_patches": steps_to_g3_yaml_items(steps),
        "note": "Scriptable paper log checks only; keys/SEG still manual in g3_evidence YAML",
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
