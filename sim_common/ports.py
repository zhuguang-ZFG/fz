#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TCP port helpers for starting grblHAL_sim without bind clashes."""

from __future__ import annotations

import socket
import time
from typing import Optional


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.25)
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def find_free_port(
    preferred: int,
    host: str = "127.0.0.1",
    span: int = 40,
) -> int:
    """Return preferred if free, else preferred+1.. within span, else OS ephemeral."""
    for p in range(preferred, preferred + span):
        if not port_listening(p, host):
            # double-check bind
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, p))
                s.close()
                return p
            except OSError:
                try:
                    s.close()
                except OSError:
                    pass
                continue
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def wait_port(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 8.0,
) -> bool:
    """Poll until TCP accept works. Brief connect then close (server must multi-accept)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_listening(port, host):
            # second probe after tiny gap — reduces false ready
            time.sleep(0.15)
            if port_listening(port, host):
                return True
        time.sleep(0.12)
    return False
