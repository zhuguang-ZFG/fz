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
# 豁免只认真 ready：Grbl 主循环提示符行。默认标记 "Grbl" 会被
# [MSG:Grbl_ESP32 Ver ...] 横幅满足，拦不住「卡在 ready 之前」的启动。
QEMU_STRONG_READY_RE = re.compile(r"Grbl[^\n]*\['\$' for help\]", re.IGNORECASE)


def analyze_startup_log(
    text: str,
    ready_markers: Iterable[str],
    max_boots: int = 2,
    qemu_ipc_guru_exemption: bool = False,
) -> Dict[str, Any]:
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
    artifact_exemptions: List[Dict[str, Any]] = []
    if qemu_ipc_guru_exemption and fatal_events:
        # QEMU 首轮 POWERON 在应用入口的 ipc_task/crosscore yield 必现一次性
        # Guru BREAK（仿真多核 IPC 保真缺口，2026-10-03 判别实验符号化钉死），
        # SW_CPU_RESET 后 boot2 干净。判据全部成立才把这一次事件记为
        # 仿真 artifact；任何额外异常都回落为 fail，不允许借豁免混过。
        guru_lines = {
            event["line"]
            for event in fatal_events
            if event["kind"] in {"guru_meditation", "panic"}
        }
        other_events = [
            event
            for event in fatal_events
            if event["kind"] not in {"guru_meditation", "panic"}
        ]
        first_msg_line = next(
            (n for n, line in enumerate(lines, start=1) if "[MSG:" in line),
            None,
        )
        if (
            len(guru_lines) == 1
            and not other_events
            and first_msg_line is not None
        ):
            incident = next(iter(guru_lines))
            kinds_on_line = {
                event["kind"] for event in fatal_events if event["line"] == incident
            }
            if (
                {"guru_meditation", "panic"} <= kinds_on_line
                and incident < first_msg_line
                and boot_count == 2
                and not restart_loop
                and (not markers or ready_hits)
                and QEMU_STRONG_READY_RE.search(text)
            ):
                artifact_exemptions.append(
                    {
                        "kind": "qemu_first_boot_ipc_guru",
                        "line": incident,
                        "note": (
                            "QEMU 多核 IPC 仿真缺口（推断）：首轮应用入口一次性 Guru BREAK，"
                            "boot2 已达 ready；本批未做实机验证，按仿真保真缺口登记"
                        ),
                    }
                )
                fatal_events = [
                    event for event in fatal_events if event["line"] != incident
                ]
    return {
        "status": "pass" if not fatal_events else "fail",
        "ready_markers": markers,
        "ready_hits": ready_hits,
        "boot_count": boot_count,
        "restart_loop": restart_loop,
        "fatal_events": fatal_events,
        "artifact_exemptions": artifact_exemptions,
        "uart_line_count": len(lines),
    }
