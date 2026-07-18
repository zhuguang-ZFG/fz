#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import importlib.util
import json
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

FZ_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("fz_mcp_server", FZ_ROOT / "scripts" / "fz_mcp_server.py")
assert SPEC and SPEC.loader
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)


class TestFzMcpServer(unittest.IsolatedAsyncioTestCase):
    async def test_tools_mirror_agent_api_schemas(self) -> None:
        tools = await MCP.SERVER.request_handlers[MCP.types.ListToolsRequest](MCP.types.ListToolsRequest(method="tools/list"))
        by_name = {tool.name: tool for tool in tools.root.tools}
        self.assertEqual(set(by_name), set(MCP.TOOL_NAMES))
        self.assertNotIn("grbl_root", by_name["run_machine_pin_erc"].inputSchema["properties"])
        self.assertIn("timeout_s", by_name["run_machine_pin_erc"].inputSchema["properties"])

    async def test_tool_call_delegates_to_agent_api(self) -> None:
        envelope = {"ok": True, "operation": "run_machine_pin_erc", "result": {"status": "pass"}}
        with mock.patch.object(MCP, "_handle", return_value=envelope) as handle:
            result = await MCP.SERVER.request_handlers[MCP.types.CallToolRequest](
                MCP.types.CallToolRequest(method="tools/call", params={"name": "run_machine_pin_erc", "arguments": {"timeout_s": 10}})
            )
        handle.assert_called_once_with("run_machine_pin_erc", {"timeout_s": 10})
        self.assertEqual(json.loads(result.root.content[0].text), envelope)
        self.assertEqual(result.root.structuredContent, envelope)
        self.assertFalse(result.root.isError)

    async def test_agent_api_failure_becomes_mcp_tool_error(self) -> None:
        envelope = {"ok": False, "operation": "run_gate", "error": {"code": "busy"}}
        with mock.patch.object(MCP, "_handle", return_value=envelope):
            result = await MCP.SERVER.request_handlers[MCP.types.CallToolRequest](
                MCP.types.CallToolRequest(method="tools/call", params={"name": "run_gate", "arguments": {}})
            )
        self.assertTrue(result.root.isError)
        self.assertEqual(result.root.structuredContent, envelope)

    async def test_long_tool_does_not_block_resource_handler(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def handle(operation: str, params: dict) -> dict:
            if operation == "run_gate":
                started.set()
                release.wait(timeout=2)
            return {"ok": True, "operation": operation, "result": params}

        tool_handler = MCP.SERVER.request_handlers[MCP.types.CallToolRequest]
        resource_handler = MCP.SERVER.request_handlers[MCP.types.ReadResourceRequest]
        with mock.patch.object(MCP, "_handle", side_effect=handle):
            tool_task = asyncio.create_task(
                tool_handler(MCP.types.CallToolRequest(method="tools/call", params={"name": "run_gate", "arguments": {}}))
            )
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            before = time.monotonic()
            resource = await asyncio.wait_for(
                resource_handler(MCP.types.ReadResourceRequest(method="resources/read", params={"uri": "fz://describe"})),
                timeout=1,
            )
            self.assertLess(time.monotonic() - before, 0.9)
            self.assertEqual(json.loads(resource.root.contents[0].text)["operation"], "describe")
            release.set()
            await tool_task

    async def test_resources_are_fixed_and_allowlisted(self) -> None:
        result = await MCP.SERVER.request_handlers[MCP.types.ListResourcesRequest](MCP.types.ListResourcesRequest(method="resources/list"))
        uris = {str(resource.uri).rstrip("/") for resource in result.root.resources}
        self.assertIn("fz://describe", uris)
        self.assertIn("fz://report/machine_pin_erc", uris)
        self.assertFalse(any(".." in uri for uri in uris))

    async def test_report_resource_delegates_to_whitelisted_read(self) -> None:
        envelope = {"ok": True, "operation": "read_report", "result": {"status": "pass"}}
        with mock.patch.object(MCP, "_handle", return_value=envelope) as handle:
            result = await MCP.SERVER.request_handlers[MCP.types.ReadResourceRequest](
                MCP.types.ReadResourceRequest(method="resources/read", params={"uri": "fz://report/machine_pin_erc"})
            )
        handle.assert_called_once_with("read_report", {"name": "machine_pin_erc"})
        self.assertEqual(json.loads(result.root.contents[0].text), envelope)

    def test_schemas_have_no_moonshot_invalid_combinators(self) -> None:
        # Regression guard for the Moonshot 400: a schema node must never carry a
        # combinator (anyOf/oneOf/allOf) as a sibling of `type`, or Kimi rejects
        # tools/list and the whole session fails. _mcp_tool_schema must strip these.
        def offenders(node, path="root"):
            found = []
            if isinstance(node, dict):
                if "type" in node and any(c in node for c in ("anyOf", "oneOf", "allOf")):
                    found.append(path)
                for key, value in node.items():
                    found.extend(offenders(value, f"{path}.{key}"))
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    found.extend(offenders(value, f"{path}[{index}]"))
            return found

        for name in MCP.TOOL_NAMES:
            schema = MCP._mcp_tool_schema(name)
            self.assertEqual(offenders(schema), [], f"{name} advertises a Moonshot-invalid schema")

    async def test_every_run_tool_carries_annotations(self) -> None:
        tools = await MCP.SERVER.request_handlers[MCP.types.ListToolsRequest](
            MCP.types.ListToolsRequest(method="tools/list")
        )
        for tool in tools.root.tools:
            annotations = tool.annotations
            self.assertIsNotNone(annotations, f"{tool.name} is missing annotations")
            self.assertFalse(annotations.readOnlyHint, f"{tool.name} spawns subprocesses; not read-only")
            self.assertFalse(annotations.destructiveHint, f"{tool.name} overwrites its own report; not destructive")
            self.assertTrue(annotations.idempotentHint, f"{tool.name} reruns deterministically; idempotent")
            self.assertFalse(annotations.openWorldHint, f"{tool.name} is a closed-world local simulation")


if __name__ == "__main__":
    unittest.main()
