#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Virtual I/O plant for grblHAL_sim.

Community (grblHAL Simulator README + grbl_interface.c):
  - TCP realtime: ! hold, ~ cycle start, 0x18 reset
  - stdin keys: H hold pin, S start, x/y/z limits, … (console; unreliable via pipe on Windows)

Automated tests should use TCP realtime with -t 1 so motion is still Run.
"""

from __future__ import annotations

import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


# Stdin key map from grblHAL Simulator src/grbl_interface.c
STDIN_KEYS = {
    "estop": "e",
    "reset_pin": "r",
    "feed_hold_pin": "h",
    "cycle_start_pin": "s",
    "door": "d",
    "probe": "p",
    "probe_connected": "o",
    "limit_x_min": "x",
    "limit_y_min": "y",
    "limit_z_min": "z",
    "limit_x_max": "X",
    "limit_y_max": "Y",
    "limit_z_max": "Z",
}


@dataclass
class PlantEvent:
    name: str
    method: str  # tcp_realtime | stdin
    detail: str = ""
    ok: bool = True


@dataclass
class Plant:
    """Inject control events into a running sim."""

    sock: socket.socket
    proc: Optional[subprocess.Popen] = None
    log: List[PlantEvent] = field(default_factory=list)

    def tcp_byte(self, b: bytes, name: str) -> None:
        self.sock.sendall(b)
        self.log.append(PlantEvent(name=name, method="tcp_realtime", detail=repr(b)))

    def feed_hold(self) -> None:
        """Grbl realtime feed hold (!)."""
        self.tcp_byte(b"!", "feed_hold")

    def cycle_start(self) -> None:
        """Grbl realtime cycle start / resume (~)."""
        self.tcp_byte(b"~", "cycle_start")

    def soft_reset(self) -> None:
        self.tcp_byte(b"\x18", "soft_reset")

    def stdin_key(self, key: str, name: Optional[str] = None) -> bool:
        """
        Toggle GPIO via sim stdin (needs console-style stdin).
        Returns False if process has no stdin pipe.
        """
        label = name or key
        if self.proc is None or self.proc.stdin is None:
            self.log.append(
                PlantEvent(name=label, method="stdin", detail="no stdin", ok=False)
            )
            return False
        ch = STDIN_KEYS.get(key, key)
        if len(ch) != 1:
            self.log.append(
                PlantEvent(name=label, method="stdin", detail=f"bad key {key}", ok=False)
            )
            return False
        try:
            self.proc.stdin.write(ch.encode("ascii"))
            self.proc.stdin.flush()
            self.log.append(PlantEvent(name=label, method="stdin", detail=ch))
            return True
        except OSError as exc:
            self.log.append(
                PlantEvent(name=label, method="stdin", detail=str(exc), ok=False)
            )
            return False

    def pulse_feed_hold_pin(self) -> bool:
        """Toggle hold pin twice (press/release) via stdin if available."""
        ok1 = self.stdin_key("feed_hold_pin", "hold_pin_down")
        time.sleep(0.05)
        ok2 = self.stdin_key("feed_hold_pin", "hold_pin_up")
        return ok1 and ok2
