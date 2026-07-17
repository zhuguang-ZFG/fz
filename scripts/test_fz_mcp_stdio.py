#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

FZ_ROOT = Path(__file__).resolve().parent.parent
SERVER = FZ_ROOT / "scripts" / "fz_mcp_server.py"


class TestFzMcpStdio(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_initialize_tools_and_resources(self) -> None:
        env = dict(os.environ)
        env.setdefault("PYTHONUTF8", "1")
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER)],
            cwd=str(FZ_ROOT),
            env=env,
            encoding="utf-8",
            encoding_error_handler="replace",
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                self.assertEqual(initialized.serverInfo.name, "fz-pc-simulation")
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                self.assertIn("run_gate", tool_names)
                self.assertIn("run_machine_pin_erc", tool_names)
                resources = await session.list_resources()
                resource_uris = {str(resource.uri).rstrip("/") for resource in resources.resources}
                self.assertIn("fz://describe", resource_uris)
                self.assertIn("fz://report/machine_pin_erc", resource_uris)
                report = await session.read_resource("fz://report/machine_pin_erc")
                envelope = json.loads(report.contents[0].text)
                self.assertTrue(envelope["ok"])
                self.assertEqual(envelope["operation"], "read_report")


if __name__ == "__main__":
    unittest.main()
