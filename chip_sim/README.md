# chip_sim — optional ESP32 chip-level tooling (probe only by default)

**Not** the default product gate. Host SIL remains `protocol_sim` + `hardware_sim` + `win_full_sim`.

## Why this folder exists

Open-source / vendor chip simulators **do exist**:

| Tool | Docs | Role |
|------|------|------|
| Espressif QEMU | [IDF QEMU](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html) | Official CPU/peripheral SIL |
| Wokwi CLI / CI | [Wokwi CI](https://docs.wokwi.com/wokwi-ci/getting-started) | Board+serial scenarios in CI |
| Renode | [renode.io](https://renode.io/) | System emulation / multi-node |

They **do not** replace paper path / BT product acceptance or full Wi‑Fi OTA proof for this Arduino Grbl fork.

## Commands

```powershell
cd D:\Users\zhugu\fz
# inventory only (exit 0 even if tools missing)
python chip_sim/probe_chip_tools.py

# fail if no chip tool found
python chip_sim/probe_chip_tools.py --require-any

# attach firmware artifact path if built
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python chip_sim/probe_chip_tools.py --firmware-hint

# optional layer on full host stack
python scripts/win_full_sim.py --with-chip-probe
```

## Install sketches (operator)

### Espressif QEMU (Windows x86_64)

1. Install [ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html) **or** download prebuilt from [espressif/qemu releases](https://github.com/espressif/qemu/releases).  
2. Or: `python %IDF_PATH%\tools\idf_tools.py install qemu-xtensa` then export PATH.  
3. Expect `qemu-system-xtensa` on PATH.  
4. **Product caveat:** full Grbl_Esp32 Arduino image is **not** guaranteed to boot under QEMU without IDF-style flash layout / open_eth networking. Use probe + research before claiming.

### Wokwi CLI

1. Install CLI from Wokwi docs; set `WOKWI_CLI_TOKEN`.  
2. Add `wokwi.toml` + scenario under a **minimal** sketch (prefer `test_drive` subset), not full paper machine first.  
3. Free tier has monthly simulation minutes.

### Renode

1. Install from [renode.io](https://renode.io/).  
2. Map only if you need UART/GPIO experiments separate from grblHAL plant.

## Fusion catalog

See `docs/specs/2026-07-14-opensource-sim-fusion-catalog.md`.
