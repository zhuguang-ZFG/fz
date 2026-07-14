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

**Community defaults:** prefer `--flash-mode dio` (default) for QEMU merge — guest often logs `mode:DIO`; see [xtensa-qemetsu](https://github.com/deomorxsy/xtensa-qemetsu). Product `platformio.ini` may use QIO on real silicon — different world.

**Multi-source notes:** [multi-source-sim-research](../docs/specs/2026-07-14-multi-source-sim-research.md).

## Install sketches (operator)

### Espressif QEMU (Windows x86_64)

1. Preferred: `.\chip_sim\install_qemu_windows.ps1` (from [espressif/qemu releases](https://github.com/espressif/qemu/releases)).  
2. Or ESP-IDF: `python %IDF_PATH%\tools\idf_tools.py install qemu-xtensa` then export PATH.  
3. Or set `ESP_QEMU` to `qemu-system-xtensa.exe`.  
4. **Product caveat:** full Grbl_Esp32 Arduino image is **not** guaranteed to boot under QEMU.

### Wokwi（乐鑫官方第三方工具）

- **乐鑫文档：** https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html  
- **站点：** https://wokwi.com/  
- 支持：浏览器、VS Code、`wokwi-cli`、CI `--expect-text`；Wi‑Fi 仿真；**结果可能与真机不同**（官方备注）。  
- 本产品是 **Arduino/PlatformIO**，用 **`wokwi-cli` + `chip_sim/wokwi/`**，不要依赖 `idf.py wokwi`（需 IDF ≥ 6）。

```powershell
# 探测 CLI / token
python chip_sim/probe_chip_tools.py

# 仅生成 results/wokwi/wokwi.toml（需已 pio 出 firmware.bin）
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python chip_sim/run_wokwi_smoke.py --dry-run

# 真跑（需 wokwi-cli + WOKWI_CLI_TOKEN）
# $env:WOKWI_CLI_TOKEN='...'
# python chip_sim/run_wokwi_smoke.py --expect-text "Grbl"
```

脚手架：`chip_sim/wokwi/README.md`、`wokwi.toml`、`diagram.json`。  
**Free 档有仿真分钟额度；不进 `agent_gate` 硬门禁。**

### Renode

1. Install from [renode.io](https://renode.io/).  
2. Map only if you need UART/GPIO experiments separate from grblHAL plant.

## Fusion catalog

See `docs/specs/2026-07-14-opensource-sim-fusion-catalog.md`.
