#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse grblHAL_sim -s step logs and estimate axis travel from step counts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


# "    15.49800 1, 0, 0, 0"
_STEP_LINE = re.compile(
    r"^\s*([\d.]+)\s+(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*$"
)


@dataclass
class StepSample:
    t: float
    steps: Tuple[int, int, int, int]  # X,Y,Z,A (as printed)


def parse_step_log(path: Path) -> List[StepSample]:
    """Return all step samples from a grblHAL -s log file."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    out: List[StepSample] = []
    for line in text.splitlines():
        m = _STEP_LINE.match(line)
        if not m:
            continue
        out.append(
            StepSample(
                t=float(m.group(1)),
                steps=(
                    int(m.group(2)),
                    int(m.group(3)),
                    int(m.group(4)),
                    int(m.group(5)),
                ),
            )
        )
    return out


def max_abs_steps(samples: Sequence[StepSample]) -> Tuple[int, int, int, int]:
    """Max absolute cumulative step count seen per axis."""
    mx = [0, 0, 0, 0]
    for s in samples:
        for i in range(4):
            mx[i] = max(mx[i], abs(s.steps[i]))
    return mx[0], mx[1], mx[2], mx[3]


def steps_delta(
    before: Sequence[StepSample], after: Sequence[StepSample]
) -> Tuple[int, int, int, int]:
    """
    Delta of max-abs cumulative counters between two snapshots.
    Logs are process-global cumulative; use before/after max abs.
    """
    b = max_abs_steps(before) if before else (0, 0, 0, 0)
    a = max_abs_steps(after) if after else b
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2], a[3] - b[3])


def mm_from_steps(
    steps: Sequence[int], steps_per_mm: Sequence[float]
) -> Tuple[float, float, float]:
    """Convert step counts to mm for XYZ using $100/$101/$102 style values."""
    out = []
    for i in range(3):
        spm = float(steps_per_mm[i]) if i < len(steps_per_mm) else 250.0
        if spm == 0:
            out.append(0.0)
        else:
            out.append(steps[i] / spm)
    return out[0], out[1], out[2]


def assert_travel_mm(
    delta_steps: Sequence[int],
    expect_mm: Sequence[float],
    steps_per_mm: Sequence[float],
    eps_mm: float = 0.5,
) -> Tuple[bool, str, Tuple[float, float, float]]:
    """
    Check |mm_from_steps - expect| <= eps per axis.
    Returns (ok, detail, actual_mm).
    """
    actual = mm_from_steps(delta_steps, steps_per_mm)
    for i in range(3):
        exp = float(expect_mm[i]) if i < len(expect_mm) else 0.0
        if abs(actual[i] - exp) > eps_mm:
            return (
                False,
                f"axis{i}: got {actual[i]:.3f}mm want {exp}mm "
                f"(steps={delta_steps[i]}, spm={steps_per_mm[i]}, eps={eps_mm})",
                actual,
            )
    return True, "ok", actual
