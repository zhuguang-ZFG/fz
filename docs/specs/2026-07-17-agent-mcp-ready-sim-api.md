# Agent MCP-ready PC simulation API

## Decision

Keep simulation engines and report generation independent from MCP transports.
`scripts/agent_api.py` is the stable application boundary; a future MCP server
should be a thin adapter over this module.

## Evidence

- MCP Python SDK v1.x is the stable production line. Its official model separates
  side-effecting tools from read-only resources and supports stdio, SSE, and
  Streamable HTTP. The v2 line is still pre-release, so fz does not depend on it.
- Espressif `pytest-embedded` composes DUT capabilities as optional services
  (`serial`, `qemu`, `arduino`, `wokwi`) instead of coupling tests to one target.
- grblHAL Simulator exposes TCP control plus stdin hardware-event injection.
- Wokwi CI uses explicit scenarios, timeouts, expected text, failure text, and
  serial-log artifacts.
- Renode exposes programmatic Python control (`pyrenode3`) and repeatable tests.

## API boundary

The JSON envelope contains a version, request ID, operation, timestamp, success
status, forbidden claims, and either a result or structured error. Commands are
constructed from enumerated profiles and discovered/whitelisted case names;
callers cannot submit shell fragments or arbitrary file paths.
`describe` returns JSON Schema-style parameter contracts suitable for direct MCP
tool registration. A stale execution lock is recovered only when its recorded
process no longer exists; malformed locks remain conservative `busy` failures.

Initial operations:

| Operation | MCP mapping | Purpose |
|-----------|-------------|---------|
| `describe` | resource | Capability/schema discovery |
| `list_cases` | resource | Discover protocol/hardware scenarios |
| `list_scenarios` | resource | Discover validated product-policy scenarios |
| `read_report` | resource | Read named, whitelisted JSON evidence |
| `run_gate` | tool | Run an allowed gate profile |
| `rerun_cases` | tool | Rerun named protocol/hardware cases |
| `run_product_trace` | tool | Run the firmware-owned protocol policy trace |
| `run_differential` | tool | Compare that policy with isolated grblHAL responses |
| `run_scenarios` | tool | Run whitelisted scenarios and return minimal failure evidence |
| `list_qwen_profiles` | resource | Discover existing QWEN evidence profiles |
| `run_qwen_gate` | tool | Run fixed QWEN pytest/FakeDevice/drawing evidence profile |

The product trace supports a fixed `stateful_modal` switch that emits per-line
`modal_before`/`modal_after` evidence for scenario replay. The product trace/
differential tools accept only fixed boolean policy switches and bounded timeouts; they do not accept caller-supplied G-code, paths, or commands. Execution operations use an exclusive lock because current `*_last.json` files
are shared mutable state. They support bounded timeouts and return only output
tails plus structured report content.
The CLI forces stdin/stdout/stderr to UTF-8 so stdio transports remain valid JSON
on Windows hosts whose inherited console encoding is GBK.

## Future MCP adapter

Use the stable SDK line (`mcp>=1.27,<2`) until v2 is stable. Map tools/resources
directly to `agent_api.handle()` or typed wrappers around `dispatch()`; do not
duplicate subprocess construction in the MCP layer. Start with stdio for local
agents. Add Streamable HTTP only after authentication, workspace allowlisting,
concurrency policy, cancellation, and artifact retention are designed.

## Deliberate limits

- Host SIL does not prove paper mechanics, real Bluetooth, Wi-Fi OTA, product
  flashing, or successful QEMU application boot.
- The API does not expose arbitrary commands or arbitrary filesystem reads.
- The first version serializes execution; read-only discovery/report calls remain
  available without acquiring the execution lock.
