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


def last_steps(samples: Sequence[StepSample]) -> Tuple[int, int, int, int]:
    """Last printed cumulative counters (signed)."""
    if not samples:
        return (0, 0, 0, 0)
    return samples[-1].steps


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


def snapshot_max_abs(path: Path) -> Tuple[int, int, int, int]:
    """Convenience: max-abs steps currently in log file."""
    return max_abs_steps(parse_step_log(path))


def per_move_delta(
    before_snap: Sequence[int], after_snap: Sequence[int]
) -> Tuple[int, int, int, int]:
    """Delta between two max-abs snapshots (per-move window)."""
    b = list(before_snap) + [0, 0, 0, 0]
    a = list(after_snap) + [0, 0, 0, 0]
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2], a[3] - b[3])


def samples_in_time_window(
    samples: Sequence[StepSample], t0: float, t1: float
) -> List[StepSample]:
    """Samples with t in [t0, t1]."""
    if t1 < t0:
        t0, t1 = t1, t0
    return [s for s in samples if t0 <= s.t <= t1]


def window_travel_steps(
    samples: Sequence[StepSample], t0: float, t1: float
) -> Tuple[int, int, int, int]:
    """
    Travel inside a sim-time window using first/last cumulative counters.
    Prefer |last - first| per axis (handles direction).
    """
    win = samples_in_time_window(samples, t0, t1)
    if len(win) < 2:
        # fall back to max-abs in window vs empty
        if not win:
            return (0, 0, 0, 0)
        return tuple(abs(x) for x in win[-1].steps)  # type: ignore
    first, last = win[0].steps, win[-1].steps
    return (
        abs(last[0] - first[0]),
        abs(last[1] - first[1]),
        abs(last[2] - first[2]),
        abs(last[3] - first[3]),
    )


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
            out.append(abs(steps[i]) / spm)
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
        exp = abs(float(expect_mm[i])) if i < len(expect_mm) else 0.0
        if abs(actual[i] - exp) > eps_mm:
            return (
                False,
                f"axis{i}: got {actual[i]:.3f}mm want {exp}mm "
                f"(steps={delta_steps[i]}, spm={steps_per_mm[i]}, eps={eps_mm})",
                actual,
            )
    return True, "ok", actual
