#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse grblHAL_sim -b block logs (community planner debug surface).

Typical lines interleave with step logs; we count non-empty non-comment lines
and optional 'block number' markers seen in -s streams.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple


_BLOCK_MARK = re.compile(r"block\s*number\s*(\d+)", re.I)
_STEPISH = re.compile(
    r"^\s*([\d.]+)\s+(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*$"
)


def parse_block_log(path: Path) -> Dict[str, object]:
    if not path.is_file():
        return {"exists": False, "lines": 0, "block_marks": 0, "max_block": None}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    marks: List[int] = []
    for ln in text.splitlines():
        m = _BLOCK_MARK.search(ln)
        if m:
            marks.append(int(m.group(1)))
    return {
        "exists": True,
        "lines": len(lines),
        "block_marks": len(marks),
        "max_block": max(marks) if marks else None,
        "bytes": path.stat().st_size,
    }


def assert_block_activity(
    path: Path, *, min_lines: int = 1
) -> Tuple[bool, str, Dict[str, object]]:
    info = parse_block_log(path)
    if not info.get("exists"):
        return False, f"missing {path}", info
    nbytes = int(info.get("bytes") or 0)
    if nbytes <= 0:
        return False, "empty block log", info
    nlines = int(info.get("lines") or 0)
    nmarks = int(info.get("block_marks") or 0)
    # Activity: non-empty file with either content lines, block markers, or any bytes
    if min_lines <= 0:
        return True, "ok", info
    if nlines >= min_lines or nmarks >= 1:
        return True, "ok", info
    return False, f"too few block lines: {info}", info
