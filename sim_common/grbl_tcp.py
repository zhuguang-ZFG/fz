#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared Grbl/grblHAL TCP client for host SIL.

Used by protocol_sim and hardware_sim so realtime/drain semantics stay aligned.
"""

from __future__ import annotations

import re
import socket
import time
from typing import List, Optional, Sequence, Tuple

OK_RE = re.compile(r"^ok\s*$", re.I)
ERROR_RE = re.compile(r"error:(\d+)", re.I)
ALARM_RE = re.compile(r"ALARM:(\d+)", re.I)
MPOS_RE = re.compile(r"MPos:([-\d.]+),([-\d.]+),([-\d.]+)")

DEFAULT_TIMEOUT = 5.0
BOOT_WAIT = 0.55


class GrblTcp:
    """Line-oriented Grbl client over TCP (sim -p port)."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = DEFAULT_TIMEOUT,
        boot_wait: float = BOOT_WAIT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.boot_wait = boot_wait
        self.sock: Optional[socket.socket] = None
        self._buf = b""

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        time.sleep(self.boot_wait)
        self._drain()

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _drain(self) -> List[str]:
        lines: List[str] = []
        if not self.sock:
            return lines
        self.sock.settimeout(0.12)
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
                while b"\n" in self._buf:
                    raw, self._buf = self._buf.split(b"\n", 1)
                    text = raw.decode("utf-8", errors="replace").strip("\r")
                    if text:
                        lines.append(text)
        except (socket.timeout, BlockingIOError):
            pass
        finally:
            if self.sock:
                self.sock.settimeout(self.timeout)
        return lines

    def send_line(self, line: str, wait: float = 0.5) -> List[str]:
        if not self.sock:
            raise RuntimeError("not connected")
        self.sock.sendall((line.rstrip("\r\n") + "\n").encode("utf-8"))
        deadline = time.time() + max(wait, 0.1)
        collected: List[str] = []
        while time.time() < deadline:
            got = self._drain()
            collected.extend(got)
            if any(OK_RE.match(x) or ERROR_RE.search(x) or ALARM_RE.search(x) for x in got):
                time.sleep(0.04)
                collected.extend(self._drain())
                break
            time.sleep(0.04)
        return collected

    def soft_reset(self) -> List[str]:
        if not self.sock:
            raise RuntimeError("not connected")
        self.sock.sendall(b"\x18")
        time.sleep(0.35)
        return self._drain()

    def unlock(self) -> None:
        """Alias used by hardware_sim."""
        self.unlock_if_needed()

    def unlock_if_needed(self) -> None:
        self.send_line("$X", wait=1.0)
        self.send_line("G21 G90 G94", wait=0.8)
        self.send_line("G10 L20 P1 X0 Y0 Z0", wait=0.8)

    def send_realtime(self, b: bytes) -> None:
        if not self.sock:
            raise RuntimeError("not connected")
        self.sock.sendall(b)


def parse_mpos(responses: Sequence[str]) -> Optional[List[float]]:
    for r in responses:
        m = MPOS_RE.search(r)
        if m:
            return [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    return None


def wait_idle(
    client: GrblTcp,
    timeout: float = 30.0,
) -> Tuple[Optional[List[float]], List[str]]:
    deadline = time.time() + timeout
    collected: List[str] = []
    last_mpos: Optional[List[float]] = None
    while time.time() < deadline:
        resp = client.send_line("?", wait=0.7)
        collected.extend(resp)
        m = parse_mpos(resp)
        if m:
            last_mpos = m
        if any(x.startswith("<Idle") for x in resp) or any("<Idle" in x for x in resp):
            return last_mpos, collected
        time.sleep(0.08)
    return last_mpos, collected


def classify_responses(responses: Sequence[str]) -> Tuple[str, Optional[str]]:
    for r in responses:
        m = ERROR_RE.search(r)
        if m:
            return "error", m.group(1)
        m = ALARM_RE.search(r)
        if m:
            return "alarm", m.group(1)
    for r in responses:
        if OK_RE.match(r):
            return "ok", None
    for r in responses:
        if r.startswith("<") and r.endswith(">"):
            return "status", None
        if r.startswith("["):
            return "status", None
    return "unknown", None
