# R1 Release Gate + Hardware Sim Baseline — Implementation Plan

> **For agentic workers:** Implement task-by-task; verify with commands below.

**Goal:** Ship a working `release_gate.py` (G0/G1/G5 + honest G2–G4 skip/unknown) and a minimal `hardware_sim` runner that exercises grblHAL with motion + step log hooks.

**Architecture:** `fz` is the sim/gate home. Gate orchestrates subprocesses, writes `release/bundles/<id>/`, exit codes per pre-release design. Hardware sim reuses protocol TCP patterns and vendored `grblHAL_sim`.

**Tech Stack:** Python 3.10+, subprocess, pathlib; PlatformIO via `pio` when `GRBL_ROOT` set.

## Global Constraints

- Never claim silicon verification from grblHAL_sim alone.
- `features.paper_path=true` without G3 evidence → exit 2 or 3, not pass.
- Commit/push only in `fz` unless user asks for Grbl changes.
