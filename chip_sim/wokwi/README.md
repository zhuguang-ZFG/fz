# Wokwi 旁路（乐鑫官方第三方工具）

**官方文档（ESP32-S3 页，通用说明同样适用）：**  
https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html  

**产品站：** https://wokwi.com/

## 和本仓的关系

| 层 | 工具 | 默认门禁 |
|----|------|----------|
| 主机 SIL（协议/运动） | `agent_gate` / grblHAL_sim | **硬** |
| 芯片板级仿真 | **Wokwi**（本文） | **软 / 可选** |
| 芯片 QEMU | `run_qemu_smoke.py` | 软 / 实验 |
| 纸路/BT/真 OTA | `hil_to_gate` | 真机证据 |

乐鑫原文强调：**仿真结果可能与实际硬件不同；部署前务必在真机测试。**  
Wokwi **不能**替代 `agent_gate` 的 G-code 回归，也 **不能** 签 G3b 纸路/BT。

## 官方能力摘要（摘自乐鑫文档）

- 浏览器 / VS Code / CLion / `wokwi-cli` /（IDF 6+）`idf.py wokwi`
- Wi‑Fi 仿真、GDB、截图 CI、`--expect-text` / `--fail-text` 自动化
- 配置：`wokwi.toml` + `diagram.json`（`wokwi-cli init`）
- `idf-wokwi`：需 **ESP-IDF ≥ 6.0** + `WOKWI_CLI_TOKEN`；**不适合** 本仓主产品（Arduino-ESP32 PlatformIO）
- 本产品路径：优先 **`wokwi-cli` + 手动/PIO 构建的 bin/elf**

## 本目录文件

| 文件 | 作用 |
|------|------|
| `wokwi.toml` | 固件/ELF 路径占位（相对 GRBL_ROOT 构建产物） |
| `diagram.json` | 最小 ESP32 DevKit，无纸路外设 |
| `expect_boot.scenario.yaml` 可选 | CLI 自动化草稿 |

路径默认指向：

`{GRBL_ROOT}/.pio/build/release/firmware.bin` 与 `firmware.elf`

## 操作步骤

```powershell
# 1) 安装 CLI：https://docs.wokwi.com/wokwi-ci/cli-installation
# 2) 令牌：https://wokwi.com/dashboard/ci  →  $env:WOKWI_CLI_TOKEN='...'

cd D:\Users\zhugu\fz
python chip_sim/probe_chip_tools.py          # 看 wokwi_cli / token

# 3) 先编译产品或 test_drive
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
# cd $env:GRBL_ROOT; pio run -e release

# 4) 从本目录启动（需 CLI + token + 已构建固件）
cd chip_sim/wokwi
# 按本机路径改 wokwi.toml 后：
# wokwi-cli --timeout 15000 --expect-text "Grbl" .
# 或仅冒烟：
python ../run_wokwi_smoke.py
```

## 诚实边界

- 完整 Grbl_Esp32（Wi‑Fi/BT/纸路/I2S）在 Wokwi 上 **不保证** 启动或行为正确。  
- 建议先极简 `test_drive` / hello 验证工具链，再考虑产品 bin。  
- Free 套餐有 **仿真分钟额度**（见 Wokwi Pricing）。  
- **Agent 日常仍以 `agent_gate` 为准**；Wokwi 为可选芯片旁路。

## 参考

- 乐鑫 Wokwi 第三方工具：https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html  
- Wokwi CI：https://docs.wokwi.com/wokwi-ci/getting-started  
- ESP32 Wi‑Fi on Wokwi：https://docs.wokwi.com/guides/esp32-wifi  
- VS Code：F1 → `Wokwi: Start Simulator`  
