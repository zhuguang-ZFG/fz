# 社区「免费 ESP32 模拟器」文 vs 官方 vs 本仓（去伪存真）

**版本：** 1.0（2026-07-14）  
**触发：** 社区长文（CSDN/openvela 等转载风格）《免费ESP32模拟器：在无硬件条件下验证固件逻辑…》  
**仓库：** [zhuguang-ZFG/fz](https://github.com/zhuguang-ZFG/fz)  
**产品固件：** Arduino + PlatformIO 的 Grbl_Esp32 产品 fork（非纯 ESP-IDF 工程）

---

## 0. 一句话

| 问题 | 答案 |
|------|------|
| 免费 ESP32 仿真有没有？ | **有**：官方 [QEMU](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html)、[Host apps](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/host-apps.html)、[Wokwi 第三方](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html)、Renode |
| 社区文的 `idf.py simulate` / `set-target simulate` 能照抄吗？ | **不能**。稳定文档主路径是 **`idf.py qemu …`**，不是虚构的 `simulate` 目标 |
| 能否用该文方案替代本仓 host SIL / 发版门禁？ | **不能**。文默认 **IDF 例程**；本产品是 **Arduino Grbl 运动栈 + 纸路/BT** |
| 本仓该吸收什么？ | **分层验证纪律**（逻辑契约 → 旁路芯片 → 真机 HIL），不是假命令 |

---

## 1. 官方真实入口（可复现）

### 1.1 芯片全系统：Espressif QEMU

- 文档：[QEMU Emulator (ESP-IDF)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html)
- 源码/发行：[espressif/qemu](https://github.com/espressif/qemu)
- 典型命令（**IDF 工程**）：

```bash
# 安装（Linux/macOS/Windows x86_64 有预构建）
python $IDF_PATH/tools/idf_tools.py install qemu-xtensa qemu-riscv32
# 构建后运行（官方用法）
idf.py qemu monitor
idf.py qemu gdb
```

- 能力边界（官方/社区共识）：CPU/部分外设/eFuse/GDB 可用；**Wi‑Fi/BT 射频不真**；复杂外设/时序/DMA 竞态不可当金标准。

### 1.2 主机上跑 IDF 组件：Host apps

- 文档：[Running ESP-IDF Applications on Host](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/host-apps.html)
- 性质：**组件/应用在 host 上的实现与测试**，不是「整颗 SoC 无改动仿真」。
- 与社区文「Peripheral Model Library / API 契约」叙事**部分同源**，但官方命名与集成方式 **≠** `idf.py -DIDF_TARGET=simulate simulate`。

### 1.3 板级/教学：Wokwi

- 乐鑫第三方：[Wokwi](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html)
- 本仓脚手架：`chip_sim/wokwi/` + `chip_sim/run_wokwi_smoke.py`（R18）
- **不进** `agent_gate` 硬门禁。

### 1.4 系统级多节点：Renode

- https://renode.io/ — 多节点/外设插件强；对本产品 ROI 低于 grblHAL host SIL。

---

## 2. 社区文常见失真点（打假清单）

| 社区文说法 | 判定 | 说明 |
|------------|------|------|
| `idf.py --list-targets` 含 `simulate` | **不可信** | 稳定目标是 `esp32` / `esp32c3` 等芯片名；仿真走 **qemu 子命令**，不是独立 chip target 名「simulate」 |
| `idf.py -DIDF_TARGET=simulate simulate` | **不可信** | 官方文档路径是 `idf.py qemu …` |
| `CONFIG_IDF_TARGET="simulate"` / `sdkconfig.simulate` 模板 | **不可信/勿照抄** | 易与 host-test、qemu 配置混写；以 IDF 当前文档为准 |
| 「同一份 `.c` 零修改既 flash 又 simulate 覆盖 95% API」 | **夸大** | 对 **精简 IDF 例程** 接近；对 **Arduino 核心 + 第三方库 + 未建模外设** 不成立 |
| 行为建模与 QEMU 指令级混成一条产品线 | **概念混淆** | 必须拆开：Host/组件契约 vs QEMU 全系统 vs Wokwi 板级 |
| 示例代码大段重复粘贴 / C 文件塞 C++ lambda | **不可运行参考** | 生成文特征；勿当工程模板 |
| 「模拟器可验证 MQTT/OTA/BLE GATT 全部逻辑」 | **部分真、边界假** | 状态机/字符串协议可 mock；**空中包、弱信号、真 OTA 路径** 仍需真机/HIL |
| 用该方案替代 CNC/Grbl 烧录排错 | **错位** | Grbl 主痛点是 **G-code/运动/错误码**，主路径应是 **grblHAL_sim**，不是 blink/WiFi 模板 |

---

## 3. 与本产品 / 本仓对照

### 3.1 技术栈错位

| 维度 | 社区文默认 | Grbl_Esp32 产品 fork |
|------|------------|----------------------|
| 构建 | ESP-IDF + `idf.py` | **Arduino framework** + PlatformIO |
| 入口 | `app_main` 例程 | `Grbl_Esp32.ino` → `grbl_init` / `run_once` |
| 验证重点 | FreeRTOS/WiFi/MQTT 状态机 | **G-code 解析、规划、步进、协议 ok/error** |
| 自定义 | 少 | 纸路 / BT 状态机 / I2S 等 **产品-only** |

### 3.2 本仓分层（已落地，勿推倒）

```text
L1 高频（agent 默认）  grblHAL_sim + protocol/hardware + golden + integrity
                       scripts/agent_gate.py
L2 旁路（可选）        Wokwi smoke / Espressif QEMU smoke（chip_sim/）
L3 发版                HIL + g3/g4 + release_honesty
```

| 层 | 入口 | 硬门禁？ |
|----|------|----------|
| L1 | `python scripts/agent_gate.py` | **是**（host SIL） |
| L1 金样/假绿 | `--golden` / `--integrity-inject`（R19） | 含在 gate |
| L2 QEMU | `chip_sim/run_qemu_smoke.py` | **否**（产品 app 曾 Guru Meditation） |
| L2 Wokwi | `chip_sim/run_wokwi_smoke.py` | **否** |
| L3 | `hil_to_gate.py` + evidence YAML | 产品 scope **是** |

### 3.3 实测记忆（勿当「工具不存在」）

- **QEMU + 产品 Arduino bin：** boot 可进，**app 阶段崩溃** → 工具有、产品全栈未适配 → **out of product hard gate**（见 `RESIDUAL_GAPS_SOLUTIONS.md` §3）。
- **Wokwi + Test Drive 类 bin：** 串口可见 `Grbl` 启动线索 → 旁路 smoke，不签字纸路/BT。
- **host SIL：** 解析/错误/运动契约 **可绿、可 agent 主动跑**；≠ 机电/纸路。

---

## 4. 可吸收的工程纪律（保留）

社区文**方法论**仍有用，且与 EDA 诚实度 / R17–R19 一致：

1. **分层验收**：逻辑契约 ≠ 射频 ≠ 机电。  
2. **高频反馈环**：写码 → PC 门禁 → 再改；少用「烧录看串口」排 parser。  
3. **假绿防护**：mock/harness 本身要测 → 本仓 `cases/inject` + `--integrity-inject`。  
4. **金样回放**：关键握手/错误码固定契约 → `cases/golden`。  
5. **CI 限时 + 断言关键日志**：可对 **未来极小 IDF demo** 用；**不**要求整仓迁 IDF。  
6. **条件编译隔离外设**：仅当抽取 **独立 IDF 测试桩** 时考虑；禁止为仿真撕裂产品主路径。

---

## 5. 明确不做 / 可选做

### 5.1 不做（默认）

- 把 `idf.py simulate` 写进 agent 合同或 AGENTS.md。  
- 把 Espressif QEMU 产品全栈当 `agent_gate` hard layer。  
- 为跑 QEMU 迁移整棵 Grbl_Esp32 到纯 IDF。  
- 用社区文代码片段当仓库脚手架。

### 5.2 可选（低优先级实验）

| 项 | 目的 | 验收 |
|----|------|------|
| 极小 IDF hello + `idf.py qemu monitor` | 证明本机工具链 | UART 打出固定字符串；**不**链接产品 |
| 文档交叉链 | 防 agent 照抄假命令 | 本文件 + fusion catalog + RESIDUAL_GAPS |
| Host apps 单测某个纯算法组件 | 若未来抽公共 C 库 | 与 Grbl 主循环解耦 |

---

## 6. Agent 纪律（抄这段即可）

```text
WHEN 看到「idf.py simulate / TARGET=simulate / 无硬件验全固件」：
  → 打开本文件；默认拒绝把该路径当产品门禁。

WHEN 要 PC 上抓 parser/motion/error：
  → cd fz && python scripts/agent_gate.py

WHEN 要芯片线索：
  → chip_sim/probe_chip_tools.py 或 run_qemu_smoke / run_wokwi_smoke
  → 禁止 claims: product_flash_ok / chip_qemu_app_ok / paper_bt_verified

WHEN 发版：
  → release_honesty + HIL evidence；host 绿不够。
```

---

## 7. 参考链接

- [ESP-IDF QEMU](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html)  
- [Host applications](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/host-apps.html)  
- [Wokwi (Espressif third-party)](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html)  
- 本仓：`docs/specs/2026-07-14-opensource-sim-fusion-catalog.md`  
- 本仓：`docs/RESIDUAL_GAPS_SOLUTIONS.md`  
- 本仓：`docs/AGENT_VIBE_CODING.md`  
- 本仓：`docs/STATUS.md`（R9/R18/R19）

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-14 | 初版：社区文纠偏 + 官方入口 + 本仓 L1–L3 映射 |
