#!/usr/bin/env python3
"""Classify ESP32 startup UART logs for pre-HIL initialization failures."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

FATAL_PATTERNS = {
    "guru_meditation": re.compile(r"Guru Meditation Error", re.IGNORECASE),
    "panic": re.compile(r"panic(?:'ed)?|abort\(\) was called", re.IGNORECASE),
    "watchdog": re.compile(r"watchdog|task_wdt|interrupt wdt", re.IGNORECASE),
    "brownout": re.compile(r"brownout detector was triggered", re.IGNORECASE),
    "task_allocation": re.compile(r"failed to create task|task create failed", re.IGNORECASE),
    "filesystem_mount": re.compile(r"(?:spiffs|littlefs|fatfs).{0,40}(?:mount failed|failed to mount)", re.IGNORECASE),
    "radio_init": re.compile(r"(?:bt|bluetooth|wifi).{0,40}(?:init failed|failed to init)", re.IGNORECASE),
    "i2s_init": re.compile(r"i2s.{0,40}(?:install failed|init failed|failed to init)", re.IGNORECASE),
}
BOOT_PATTERN = re.compile(r"rst:0x|ets Jun\s+8\s+2016|ESP-ROM", re.IGNORECASE)


def analyze_startup_log(text: str, ready_markers: Iterable[str], max_boots: int = 2) -> Dict[str, Any]:
    markers = [marker for marker in ready_markers if marker]
    fatal_events: List[Dict[str, Any]] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        for kind, pattern in FATAL_PATTERNS.items():
            if pattern.search(line):
                fatal_events.append({"kind": kind, "line": line_number, "text": line[:300]})
    boot_count = len(BOOT_PATTERN.findall(text))
    ready_hits = [marker for marker in markers if marker.lower() in text.lower()]
    restart_loop = boot_count > max_boots
    if restart_loop:
        fatal_events.append({"kind": "restart_loop", "boot_count": boot_count, "maximum": max_boots})
    if markers and not ready_hits:
        fatal_events.append({"kind": "ready_timeout", "expected_markers": markers})
    return {
        "status": "pass" if not fatal_events else "fail",
        "ready_markers": markers,
        "ready_hits": ready_hits,
        "boot_count": boot_count,
        "restart_loop": restart_loop,
        "fatal_events": fatal_events,
        "uart_line_count": len(lines),
    }
