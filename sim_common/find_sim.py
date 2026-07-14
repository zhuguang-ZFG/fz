#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locate vendored / env grblHAL_sim and validator."""

from __future__ import annotations

import os
from pathlib import Path
from shutil import which
from typing import Optional

FZ_ROOT = Path(__file__).resolve().parent.parent
VENDOR_SIM = FZ_ROOT / "vendor" / "grblhal_sim" / "bin"


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def _which_any(*names: str) -> Optional[Path]:
    for n in names:
        w = which(n)
        if w:
            return Path(w)
    return None


def find_sim() -> Optional[Path]:
    """Prefer GRBLHAL_SIM, then vendored Windows .exe / Linux ELF, then PATH."""
    ordered: list[Optional[Path]] = [
        _env_path("GRBLHAL_SIM"),
        VENDOR_SIM / "grblHAL_sim.exe",
        VENDOR_SIM / "grblHAL_sim",
        VENDOR_SIM / "linux" / "grblHAL_sim",
        _which_any("grblHAL_sim", "grblHAL_sim.exe"),
    ]
    for cand in ordered:
        if cand is not None and Path(cand).is_file():
            return Path(cand)
    return None


def find_validator() -> Optional[Path]:
    ordered: list[Optional[Path]] = [
        _env_path("GRBLHAL_VALIDATOR"),
        VENDOR_SIM / "grblHAL_validator.exe",
        VENDOR_SIM / "grblHAL_validator",
        VENDOR_SIM / "linux" / "grblHAL_validator",
        _which_any("grblHAL_validator", "grblHAL_validator.exe"),
    ]
    for cand in ordered:
        if cand is not None and Path(cand).is_file():
            return Path(cand)
    return None
