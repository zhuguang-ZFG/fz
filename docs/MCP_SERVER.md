# fz PC simulation MCP server

`scripts/fz_mcp_server.py` is the official MCP stdio adapter for the existing
transport-neutral Agent API. It exposes 13 allowlisted simulation tools and
fixed `fz://` JSON resources. It does not duplicate simulation logic.

## Install

Use Python 3.10 or newer and install the stable MCP SDK v1 line:

```powershell
cd D:\Users\zhugu\fz
python -m venv .venv-mcp
.\.venv-mcp\Scripts\python.exe -m pip install -r requirements-mcp.txt
.\.venv-mcp\Scripts\python.exe scripts\fz_mcp_server.py --check
```

An existing virtual environment may be used instead. The currently validated
environment is `D:\QWEN3.0\.venv310` with `mcp==1.28.1`.

## Register with Codex

Codex accepts a stdio command after `--`. Use `codex.cmd` on Windows when the
PowerShell execution policy blocks the npm `.ps1` shim:

```powershell
& "$env:APPDATA\npm\codex.cmd" mcp add fz-sim `
  --env GRBL_ROOT=D:\Users\Grbl_Esp32 `
  --env QWEN_ROOT=D:\QWEN3.0 `
  -- D:\Users\zhugu\fz\.venv-mcp\Scripts\python.exe `
     D:\Users\zhugu\fz\scripts\fz_mcp_server.py

& "$env:APPDATA\npm\codex.cmd" mcp get fz-sim
```

If reusing the QWEN environment, replace the Python path with
`D:\QWEN3.0\.venv310\Scripts\python.exe`.

## Generic stdio configuration

Clients using the common JSON configuration shape can launch it as follows:

```json
{
  "mcpServers": {
    "fz-sim": {
      "command": "D:\\Users\\zhugu\\fz\\.venv-mcp\\Scripts\\python.exe",
      "args": ["D:\\Users\\zhugu\\fz\\scripts\\fz_mcp_server.py"],
      "env": {
        "GRBL_ROOT": "D:\\Users\\Grbl_Esp32",
        "QWEN_ROOT": "D:\\QWEN3.0"
      }
    }
  }
}
```

## Capabilities

- Tools include `run_gate`, `run_machine_pin_erc`, paper campaigns, product
  protocol scenarios, and QWEN/Xiaozhi evidence gates.
- Resources include capability discovery and fixed reports such as
  `fz://report/gate`, `fz://report/observe`, and
  `fz://report/machine_pin_erc`.
- Tool results include both JSON text and MCP `structuredContent`.
- Agent API failures set MCP `isError=true`.
- Execution remains serialized by the existing Agent API lock.
- MCP callers cannot pass arbitrary commands, report paths, or firmware roots.
  Product roots are controlled by the server environment.

## Validate

```powershell
.\.venv-mcp\Scripts\python.exe -m unittest `
  scripts.test_fz_mcp_server scripts.test_fz_mcp_stdio -q
```

The stdio test launches a real server subprocess, completes MCP initialization,
lists tools and resources, and reads an allowlisted report.

## Evidence boundary

MCP changes how an agent invokes the existing PC simulation; it does not make
SIL equivalent to hardware. Paper mechanics, real Bluetooth/Wi-Fi/OTA, audio
hardware, cloud voice, product flashing, and release HIL still require their
existing acceptance evidence.
