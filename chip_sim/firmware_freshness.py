#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chip 层镜像新鲜度判据（R-fresh）。

身份核实抓的是「别的机型镜像」，这里抓的是「同机型但比源码旧的镜像」——
改了固件源码却没重 build 时，QEMU/Wokwi 的启动层会把**旧固件**的表现
当成当前代码的证据（本生态 BT crash-loop 类问题的历史盲区）。

返回 None = 无法判定（没有 GRBL_ROOT / 取不到 mtime），调用方不得据此判负；
返回 True = 镜像确实旧于源码，chip 启动层证据不成立。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

SOURCE_SUFFIXES = (".h", ".hpp", ".c", ".cpp", ".ino")


def newest_source_mtime(grbl_root: Path) -> Optional[float]:
    """Newest firmware source mtime — detects builds older than the code."""
    newest: Optional[float] = None
    try:
        for p in (Path(grbl_root) / "Grbl_Esp32" / "src").rglob("*"):
            if p.suffix.lower() in SOURCE_SUFFIXES:
                m = p.stat().st_mtime
                if newest is None or m > newest:
                    newest = m
    except OSError:
        return None
    return newest


def is_firmware_stale(app_mtime: Optional[float], grbl_root: Optional[Path]) -> Optional[bool]:
    """镜像应用段是否旧于最新源码；无法判定时返回 None。"""
    if grbl_root is None or not isinstance(app_mtime, (int, float)):
        return None
    src_mtime = newest_source_mtime(Path(grbl_root))
    if src_mtime is None:
        return None
    return bool(app_mtime < src_mtime)


def stale_detail(suite: str) -> str:
    return (
        f"{suite}: 镜像应用段旧于 GRBL_ROOT src/ 最新源码——启动证据描述的是已被改动的代码。"
        " 重建后再跑：pio run -e release 然后 chip_sim/build_flash_image.py"
    )
