# 开源仿真方案目录与融合改进（去伪存真）

**版本：** 1.0（2026-07-14）  
**仓库：** [zhuguang-ZFG/fz](https://github.com/zhuguang-ZFG/fz)  
**目的：** 汇总社区/GitHub/官方「电脑上能跑」的仿真项目，说明 **能融合什么、不能假装什么**，并给出本仓落地优先级。

---

## 0. 一句话结论

| 问题 | 答案 |
|------|------|
| 主机 CNC/Grbl 仿真开源多吗？ | **多**；本仓已融合 **grblHAL Simulator** 主路径 |
| ESP32 **芯片级**有没有官方/开源解？ | **有**：[Espressif QEMU](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html)、[Wokwi CI](https://docs.wokwi.com/wokwi-ci/getting-started)、[Renode](https://renode.io/) 等 |
| 能否用芯片级替代纸路/BT 产品门禁？ | **不能**；外设/射频/机械/本 fork 自定义逻辑覆盖不全 |
| 本仓策略 | **分层融合**：主机 SIL 常绿门禁 + 芯片探针可选 + 真机 HIL 证据 |

---

## 1. 主机 / 控制器层（H-SIM-A/B/C）

| 项目 | 链接 | 能抓什么 | 与本仓关系 |
|------|------|----------|------------|
| **grblHAL Simulator** | [github.com/grblHAL/Simulator](https://github.com/grblHAL/Simulator) | G-code 协议、规划、step/block 日志、TCP `-p`、stdin 限位键 | **主引擎** `vendor/grblhal_sim` + `protocol_sim` + `hardware_sim` |
| grbl-sim（经典） | [github.com/grbl/grbl-sim](https://github.com/grbl/grbl-sim) | 旧 8-bit Grbl 主机可执行 | **不主用**；理念同源，grblHAL 已覆盖 |
| bCNC / ioSender | 各 GitHub | Sender 联调 sim | 人工工具；不进 CI 门禁 |
| Universal GCode Sender | winder/ugs | 同上 | 同上 |
| LinuxCNC / Machinekit | linuxcnc.org | 完整机床控制栈 | **不融合**（栈过重，与 ESP Grbl 产品无关） |

**已融合改进：**

- 协议回归 + 负例加厚（`protocol_sim/cases`）  
- StepOracle + plant feed-hold（`hardware_sim`）  
- Windows 一键 `scripts/win_full_sim.py`  

**仍可加深（主机侧）：**

- 公共 `GrblTcp` 去重（protocol/hardware 两套 client）  
- 用例 JSON schema 统一  
- 有 console 时 stdin 限位 hard case（Windows 弱）

---

## 2. ESP32 芯片级 / 外设级（H-SIM-D）

### 2.1 官方 / 准官方

| 项目 | 链接 | 能力 | 对本产品的硬限制 |
|------|------|------|------------------|
| **Espressif QEMU** | [IDF QEMU guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html) · [espressif/qemu](https://github.com/espressif/qemu) | Xtensa/RISC-V 指令、部分外设、eFuse、GDB、`idf.py qemu` | 面向 **ESP-IDF** 工作流；**Wi‑Fi/BT 弱或不完整**；本仓是 **Arduino-ESP32 + 重度定制**，`.bin` 未必能直接当 IDF flash 镜像跑通全栈 |
| ESP-IDF pytest-embedded | 乐鑫文档 | host / target / qemu 分层测 | 需 IDF 工程结构；融合成本高 |
| 社区 qemu_esp32 历史 fork | Ebiroll 等 | 早期实验 | **过时**；用官方 fork |

**Windows：** 官方文档写明有 **x86_64 Windows 预构建**（`idf_tools.py install qemu-xtensa` 或 [espressif/qemu releases](https://github.com/espressif/qemu/releases)）。

### 2.2 商业+开源混合（仿真云/CLI）

| 项目 | 链接 | 能力 | 限制 |
|------|------|------|------|
| **Wokwi** | [wokwi.com](https://wokwi.com) · [乐鑫官方第三方工具页](https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32s3/third-party-tools/wokwi.html) · [CI](https://docs.wokwi.com/wokwi-ci/getting-started) | 板级仿真、Wi‑Fi、GDB、CLI/`idf.py wokwi`(IDF6+)；本仓脚手架 `chip_sim/wokwi/` | **额度/token**；Arduino 产品全栈不保证；**不进 agent_gate 硬门禁** |
| linux.do 等社区 | 推荐 Wokwi 作教学/小项目仿真 | 验证「有人在用」 | 非 CNC 写字机全栈 |

### 2.3 系统级多节点

| 项目 | 链接 | 能力 | 限制 |
|------|------|------|------|
| **Renode** (Antmicro) | [renode.io](https://renode.io/) · GitHub antmicro/renode | UART/GPIO/总线级、CI 友好、多节点 | ESP32 支持深度因平台而异；**不是** Grbl 运动植物替代品 |
| QEMU + open_eth 等 | 乐鑫 toolchain-docs | 有线网络实验 | 与产品 Wi‑Fi SoftAP 不等价 |

### 2.4 真硅无电机（H-SIM-E，非仿真器但常被混谈）

| 手段 | 说明 |
|------|------|
| `test_drive.h` + 串口 | 真芯片、无 pin；本仓 `hil/` |
| Golioth HIL | 常驻板 CI；社区高可靠路径 |

---

## 3. 云 / 契约层（软件全链路 SIL）

| 资产 | 位置 | 融合 |
|------|------|------|
| FakeDevice / motion_contract | `D:/QWEN3.0` | `scripts/run_g2_qwen_contracts.py` |
| Pact 式契约思想 | 业界 | 填满错误码表，不另起神话 Twin |

---

## 4. 融合架构（本仓落地）

```text
                    ┌─────────────────────────────────────┐
                    │  scripts/win_full_sim.py              │
                    │  L0 preflight · L1 protocol · L2 hw   │
                    │  L3 unit · L4 honesty · L5 chip probe │
                    └─────────────────────────────────────┘
           │                │                 │
           ▼                ▼                 ▼
   grblHAL_sim        plant/step_oracle   chip_sim/probe
   (default hard)     (default hard)      (optional soft)
           │
           ▼
   hil_to_gate / dual_flash   ← 真硅（可选）
```

| 层 | 默认门禁 | 工具 |
|----|----------|------|
| 协议+运动主机 | **硬** | grblHAL_sim |
| 云契约 | 可选 G2 | QWEN pytest |
| 芯片 QEMU/Wokwi/Renode | **软/可选** | `chip_sim/probe_chip_tools.py` |
| 纸路/BT/OTA | **证据/真机** | g3/g4 YAML + hil |

---

## 5. 明确不做的融合

1. 把 Wokwi/QEMU 绿当作 G3b 纸路通过。  
2. 在固件仓堆 QEMU 全量子模块（体积/许可/路径爆炸）——探针与文档住 **fz**。  
3. 用 Renode 重写步进规划器。  
4. 宣称「芯片级仿真已覆盖全部固件问题」。

---

## 6. 推荐落地顺序（ROI）

| 优先级 | 项 | 状态 |
|--------|-----|------|
| P0 | grblHAL 协议+植物+win_full_sim | **done** |
| P1 | 开源目录 + chip 工具探针 + 可选 L5 | **本版** |
| P2 | 本机安装 Espressif QEMU 后尝试 `test_drive` 启动串口冒烟 | 环境依赖 |
| P3 | Wokwi CLI token + 最小 `test_drive` scenario | 可选 CI |
| P4 | 公共 GrblTcp / 用例 schema | 工程债 |
| P5 | 实验室常驻板 HIL | 人/硬件 |

---

## 7. 参考链接速查

- grblHAL Simulator: https://github.com/grblHAL/Simulator  
- Espressif QEMU IDF: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html  
- espressif/qemu: https://github.com/espressif/qemu  
- WiFi 不在 QEMU：https://github.com/espressif/esp-idf/issues/15087  
- PIO+QEMU 社区 POC：https://github.com/deomorxsy/xtensa-qemetsu  
- OpenEth 上网：https://productionesp32.com/posts/internet-in-qemu/  
- Wokwi CI: https://docs.wokwi.com/wokwi-ci/getting-started  
- wokwi-ci-action: https://github.com/wokwi/wokwi-ci-action  
- Renode: https://renode.io/  
- Golioth HIL: https://blog.golioth.io/golioth-hil-testing-part1/  
- **多源调研长文：** [2026-07-14-multi-source-sim-research.md](./2026-07-14-multi-source-sim-research.md)  
- 本仓 residual: `docs/RESIDUAL_GAPS_SOLUTIONS.md`
