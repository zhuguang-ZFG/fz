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

## QEMU path (experimental, optional)

Official merge + run: [esp-toolchain-docs qemu/esp32](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/esp32/README.md) · [IDF QEMU guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html).

```powershell
# 1) Install Windows xtensa QEMU into vendor/ (gitignored ~36MB tarball)
.\chip_sim\install_qemu_windows.ps1

# 2) Build 4MB flash image from PIO firmware + Arduino bootloader + partitions
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python chip_sim/build_flash_image.py

# 3) Smoke: capture UART ~12s (soft experiment — not release gate)
python chip_sim/run_qemu_smoke.py
```

**Honesty:** Arduino Grbl full stack may panic/hang; Wi‑Fi/BT incomplete; never mark G3b/OTA from this green.

## Install sketches (operator)

### Espressif QEMU (Windows x86_64)

1. Preferred: `.\chip_sim\install_qemu_windows.ps1` (from [espressif/qemu releases](https://github.com/espressif/qemu/releases)).  
2. Or ESP-IDF: `python %IDF_PATH%\tools\idf_tools.py install qemu-xtensa` then export PATH.  
3. Or set `ESP_QEMU` to `qemu-system-xtensa.exe`.  
4. **Product caveat:** full Grbl_Esp32 Arduino image is **not** guaranteed to boot under QEMU.

### Wokwi CLI

1. Install CLI from Wokwi docs; set `WOKWI_CLI_TOKEN`.  
2. Add `wokwi.toml` + scenario under a **minimal** sketch (prefer `test_drive` subset), not full paper machine first.  
3. Free tier has monthly simulation minutes.

### Renode

1. Install from [renode.io](https://renode.io/).  
2. Map only if you need UART/GPIO experiments separate from grblHAL plant.

## Fusion catalog

See `docs/specs/2026-07-14-opensource-sim-fusion-catalog.md`.
