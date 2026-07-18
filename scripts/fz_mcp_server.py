#!/usr/bin/env python3
"""MCP stdio adapter over the transport-neutral fz Agent API."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.server import ReadResourceContents

FZ_ROOT = Path(__file__).resolve().parent.parent
AGENT_API_PATH = FZ_ROOT / "scripts" / "agent_api.py"
SERVER_NAME = "fz-pc-simulation"
SERVER_VERSION = "1.0.0"
RESOURCE_PREFIX = "fz://"


def _load_agent_api() -> Any:
    spec = importlib.util.spec_from_file_location("fz_agent_api", AGENT_API_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Agent API: {AGENT_API_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve stringized (PEP 563)
    # annotations, which look up cls.__module__ in sys.modules at class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


AGENT_API = _load_agent_api()
DESCRIPTION = AGENT_API.describe()
TOOL_NAMES = tuple(DESCRIPTION["mcp_mapping"]["tools"])
RESOURCE_OPERATIONS = tuple(name for name in DESCRIPTION["mcp_mapping"]["resources"] if name != "read_report")
RESOURCE_URIS = {
    **{f"{RESOURCE_PREFIX}{name}": (name, {}) for name in RESOURCE_OPERATIONS},
    **{f"{RESOURCE_PREFIX}report/{name}": ("read_report", {"name": name}) for name in AGENT_API.REPORTS},
}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _handle(operation: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return AGENT_API.handle({"operation": operation, "params": params or {}})


def _tool_description(name: str) -> str:
    descriptions = {
        "run_gate": "Run an allowlisted PC simulation gate profile and return structured evidence.",
        "rerun_cases": "Rerun allowlisted protocol or hardware cases.",
        "run_product_trace": "Run the firmware-owned protocol policy trace.",
        "run_differential": "Compare product protocol policy with isolated grblHAL behavior.",
        "run_scenarios": "Run validated product-policy scenarios with minimal failure evidence.",
        "run_paper_plant": "Run deterministic paper mechanism fault profiles.",
        "run_paper_interactions": "Run bounded paper interaction model checks.",
        "run_paper_transients": "Run scheduled paper transient fault campaigns.",
        "run_paper_contract": "Check firmware and paper Plant contract drift.",
        "run_machine_pin_erc": "Run fail-closed EDA-style machine pin electrical-rule checks.",
        "run_qwen_gate": "Run fixed QWEN firmware, motion, drawing, or voice evidence profiles.",
        "run_xiaozhi_protocol": "Run deterministic Xiaozhi WebSocket, audio-frame, and MCP protocol scenarios.",
        "run_xiaozhi_contract": "Check Xiaozhi firmware and simulation model protocol drift.",
    }
    return descriptions.get(name, f"Run fz Agent API operation {name}.")


# All exposed tools shell out to a runner that writes results/ (not read-only),
# but they are deterministic local SIL: a rerun overwrites the same report
# (idempotent), they neither delete external data nor touch a live/product
# system (not destructive), and they never reach the network or an open world
# (allowlisted, closed-world). Read-only introspection (describe/list/read_report)
# is exposed via MCP resources, not tools. Hosts use these hints to decide
# auto-approval; every run_* tool shares the same profile.
_RUN_TOOL_ANNOTATIONS = types.ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _strip_sibling_combinators(node: Any) -> None:
    """Remove anyOf/oneOf/allOf that sit as siblings of `type`.

    Moonshot (Kimi) rejects schemas where a combinator coexists with a
    parent-level `type` ("when using anyOf, type should be defined in anyOf
    items instead of the parent schema"). These combinators only encode
    constraints the runtime already enforces (e.g. rerun_cases requires at
    least one of protocol/hardware, checked in agent_api._handle), so dropping
    them from the advertised schema is safe.
    """
    if isinstance(node, dict):
        if "type" in node:
            for combinator in ("anyOf", "oneOf", "allOf"):
                node.pop(combinator, None)
        for value in node.values():
            _strip_sibling_combinators(value)
    elif isinstance(node, list):
        for item in node:
            _strip_sibling_combinators(item)


def _mcp_tool_schema(name: str) -> Dict[str, Any]:
    schema = json.loads(json.dumps(AGENT_API.OPERATION_SCHEMAS[name]))
    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("grbl_root", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [item for item in required if item != "grbl_root"]
    _strip_sibling_combinators(schema)
    return schema


def create_server() -> Server:
    server = Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        instructions=(
            "PC SIL evidence for Grbl_Esp32 and Xiaozhi. Host simulation does not prove paper mechanics, "
            "Bluetooth, OTA, real audio, cloud voice, flashing, or HIL acceptance."
        ),
    )

    @server.list_tools()
    async def list_tools() -> List[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=_tool_description(name),
                inputSchema=_mcp_tool_schema(name),
                annotations=_RUN_TOOL_ANNOTATIONS,
            )
            for name in TOOL_NAMES
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> types.CallToolResult:
        if name not in TOOL_NAMES:
            raise ValueError(f"unknown fz tool: {name}")
        envelope = await asyncio.to_thread(_handle, name, arguments)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=_json_text(envelope))],
            structuredContent=envelope,
            isError=not bool(envelope.get("ok")),
        )

    @server.list_resources()
    async def list_resources() -> List[types.Resource]:
        resources: List[types.Resource] = []
        for uri, (operation, params) in RESOURCE_URIS.items():
            report_name = params.get("name")
            resources.append(
                types.Resource(
                    name=f"fz {report_name} report" if report_name else f"fz {operation}",
                    uri=uri,
                    description=(
                        "Read a fixed, allowlisted simulation JSON report."
                        if report_name
                        else f"Read the side-effect-free Agent API resource {operation}."
                    ),
                    mimeType="application/json",
                )
            )
        return resources

    @server.read_resource()
    async def read_resource(uri: Any) -> List[ReadResourceContents]:
        normalized = str(uri).rstrip("/")
        entry = RESOURCE_URIS.get(normalized)
        if entry is None:
            raise ValueError(f"unknown or non-allowlisted fz resource: {normalized}")
        operation, params = entry
        envelope = await asyncio.to_thread(_handle, operation, params)
        return [ReadResourceContents(content=_json_text(envelope), mime_type="application/json")]

    return server


SERVER = create_server()


async def run_stdio() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await SERVER.run(read_stream, write_stream, SERVER.create_initialization_options())


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="fz PC simulation MCP stdio server")
    parser.add_argument("--check", action="store_true", help="validate SDK import and print capabilities without starting stdio")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.check:
        print(_json_text({"server": SERVER_NAME, "version": SERVER_VERSION, "tools": list(TOOL_NAMES), "resources": sorted(RESOURCE_URIS)}))
        return 0
    asyncio.run(run_stdio())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
