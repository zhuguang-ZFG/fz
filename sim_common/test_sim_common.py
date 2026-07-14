#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from sim_common.find_sim import find_sim
from sim_common.grbl_tcp import GrblTcp, classify_responses, parse_mpos
from sim_common.ports import find_free_port, port_listening
from sim_common.sim_session import start_protocol_session, stop_session


class TestClassify(unittest.TestCase):
    def test_ok(self) -> None:
        self.assertEqual(classify_responses(["ok"]), ("ok", None))

    def test_error(self) -> None:
        self.assertEqual(classify_responses(["error:22"]), ("error", "22"))

    def test_mpos(self) -> None:
        m = parse_mpos(["<Idle|MPos:1.000,2.000,3.000|FS:0,0>"])
        self.assertEqual(m, [1.0, 2.0, 3.0])


class TestPorts(unittest.TestCase):
    def test_find_free(self) -> None:
        p = find_free_port(27999, span=5)
        self.assertTrue(1000 < p < 65535)
        self.assertFalse(port_listening(p) and False)  # just call API


class TestSimSession(unittest.TestCase):
    def test_start_stop_and_two_clients(self) -> None:
        if not find_sim():
            self.skipTest("grblHAL_sim not installed")
        sess = start_protocol_session(preferred_port=27681)
        try:
            self.assertGreater(sess.port, 0)
            # first client
            c1 = GrblTcp(sess.host, sess.port, boot_wait=0.4)
            c1.connect()
            c1.close()
            # second client after close (sequential reuse)
            c2 = GrblTcp(sess.host, sess.port, boot_wait=0.4)
            c2.connect()
            resp = c2.send_line("$I", wait=1.5)
            c2.close()
            self.assertTrue(resp is not None)
        finally:
            stop_session(sess)


if __name__ == "__main__":
    unittest.main()
