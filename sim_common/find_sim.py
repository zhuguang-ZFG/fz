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


def _env_exe(name: str, default: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    w = which(default)
    return Path(w) if w else None


def find_sim() -> Optional[Path]:
    for cand in (
        _env_exe("GRBLHAL_SIM", "grblHAL_sim.exe"),
        _env_exe("GRBLHAL_SIM", "grblHAL_sim"),
        VENDOR_SIM / "grblHAL_sim.exe",
        VENDOR_SIM / "grblHAL_sim",
    ):
        if cand is not None and Path(cand).is_file():
            return Path(cand)
    return None


def find_validator() -> Optional[Path]:
    for cand in (
        _env_exe("GRBLHAL_VALIDATOR", "grblHAL_validator.exe"),
        _env_exe("GRBLHAL_VALIDATOR", "grblHAL_validator"),
        VENDOR_SIM / "grblHAL_validator.exe",
        VENDOR_SIM / "grblHAL_validator",
    ):
        if cand is not None and Path(cand).is_file():
            return Path(cand)
    return None
