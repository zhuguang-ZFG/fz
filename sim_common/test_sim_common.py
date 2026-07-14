#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from sim_common.grbl_tcp import classify_responses, parse_mpos
from sim_common.ports import find_free_port, port_listening


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


if __name__ == "__main__":
    unittest.main()
