#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G3a serial smoke against a real ESP32 (optional).

Community: Grbl_Esp32 test_drive / FluidNC serial at 115200.
Does not cover paper/BT product paths (G3b checklist).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="G3a serial smoke")
    ap.add_argument("--port", required=True, help="e.g. COM7 or /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--timeout", type=float, default=3.0)
    args = ap.parse_args(argv)

    try:
        import serial  # type: ignore
    except ImportError:
        print("ERROR: pyserial not installed (pip install pyserial)", file=sys.stderr)
        return 2

    steps: List[Dict[str, Any]] = []
    ok = True
    ser = None
    try:
        ser = serial.Serial(args.port, args.baud, timeout=args.timeout)
        time.sleep(0.5)
        ser.reset_input_buffer()
        # soft reset
        ser.write(b"\x18")
        time.sleep(1.5)
        boot = ser.read(4096).decode("utf-8", errors="replace")
        steps.append({"step": "soft_reset", "ok": True, "snippet": boot[-400:]})

        def cmd(line: str, wait: float = 0.8) -> str:
            ser.write((line + "\n").encode("utf-8"))
            time.sleep(wait)
            return ser.read(4096).decode("utf-8", errors="replace")

        r = cmd("$X")
        steps.append({"step": "$X", "ok": "ok" in r.lower() or "error" not in r.lower(), "snippet": r[-200:]})
        r = cmd("$I")
        steps.append({"step": "$I", "ok": len(r.strip()) > 0, "snippet": r[-300:]})
        r = cmd("G21 G90")
        steps.append({"step": "G21 G90", "ok": "ok" in r.lower() or "error" not in r.lower(), "snippet": r[-100:]})
        r = cmd("G0 X0 Y0")
        steps.append({"step": "G0 X0 Y0", "ok": "ok" in r.lower() or "error" not in r.lower(), "snippet": r[-100:]})
        r = cmd("?")
        steps.append({"step": "?", "ok": "MPos" in r or "Idle" in r or "Alarm" in r, "snippet": r[-200:]})
        ok = all(s["ok"] for s in steps)
    except Exception as exc:
        ok = False
        steps.append({"step": "exception", "ok": False, "snippet": str(exc)})
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    report = {
        "layer": "G3a",
        "status": "pass" if ok else "fail",
        "port": args.port,
        "baud": args.baud,
        "steps": steps,
        "note": "G3a only — not paper/BT product acceptance",
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
