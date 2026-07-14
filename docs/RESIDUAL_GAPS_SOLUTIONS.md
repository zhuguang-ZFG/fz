# 四条残余边界的社区解法

针对上线门禁里**诚实未自动化**的四项：是否有解、社区怎么做、本仓库建议。

---

## 1. 产品纸路 / BT 真机 G3b（不能只靠仿真）

### 社区怎么做

| 实践 | 要点 |
|------|------|
| [Golioth Continuously Verified + HIL](https://blog.golioth.io/golioth-hil-testing-part1/) | 真板挂在 **self-hosted runner**；PR/release 必跑；OTA/联网类问题靠 HIL 挖 |
| [Firmware HIL CI 实践](https://reversetobuild.com/devlogs/firmware-hil-ci-pipeline/) | push 后自动 flash + 串口日志断言 |
| [Python HIL / OpenHTF](https://www.tofupilot.com/guides/hardware-in-the-loop-testing-with-python-a-practical-guide) | 半自动步骤 + 结构化结果入库 |
| FluidNC / Grbl 社区 | 纸路/按键/缓冲仍靠 **实机清单**，无完整数字孪生 |

### 可行方案（按投入）

| 方案 | 自动化程度 | 说明 |
|------|------------|------|
| **A. 电子证据 + 人工操作**（已有） | 半自动 | `g3_evidence.template.yaml` + 操作员勾选；gate 机检 |
| **B. 串口可脚本部分**（已有 G3a） | 自动 | `hil/serial_smoke.py`：boot/$I/短 G0 |
| **C. 产品序列半自动** | 中 | 扩展脚本：发 M30 序列、抓 `[PaperM30]`/`PAGE_END` 日志；键仍人工 |
| **D. 实验室常驻板 + CI runner**（Golioth 路线） | 高 | 一块 ESP 常插工控机；定时/PR 触发 flash+脚本；**不必每人常插** |

**结论：有解。** 不是仿真替代，而是 **「人工一次/实验室常驻」+ 结构化证据**。  
推荐路径：**A + B 已落地 → C（M30 串口）已实现 `hil/paper_m30_serial.py` → 有条件再 D**。

---

## 2. 真 OTA 刷机（G4 现为证据清单）

### 社区怎么做

| 实践 | 要点 |
|------|------|
| [Memfault OTA checklist](https://memfault.com/blog/ota-update-checklist-for-embedded-devices/) | 多轮、日志、回滚、版本一致 |
| [ESP RainMaker pre-prod](https://docs.rainmaker.espressif.com/) | OTA 可靠性多轮验证 |
| [pytest-embedded multi-stage OTA](https://github.com/espressif/pytest-embedded/issues/297) | 构建 → 烧录 → OTA → 复位 多阶段 |
| [ESP-IDF pytest guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/contribute/esp-idf-tests-with-pytest.html) | 官方板载测试框架（偏 IDF） |
| Golioth HIL | 明确把 **OTA 手点** 换成自动化 HIL |

### 可行方案

| 方案 | 说明 |
|------|------|
| **A. 证据清单**（已有） | `g4_ota.template.yaml` + validate；适合未常开 OTA |
| **B. USB 双版本烧录回归** | `pio run -t upload` 旧 bin → 新 bin → `$I` 版本断言（比 OTA 简单） |
| **C. 真 OTA 管道** | 设备连 Wi‑Fi → 推 OTA URL → 等重启 → 版本；需稳定 AP + 板 |
| **D. 多轮脚本** | 循环 B/C ≥3 次写 evidence 自动填 YAML |

**结论：有解。** G4 清单是 **第一阶段**；**B 已实现** `hil/dual_flash_usb.py`（pio upload ± 二次 + `$I`）。  
真 Wi-Fi OTA 仍需 C + 板与 AP。

---

## 3. 芯片 QEMU 全栈（设计 out of scope）

### 社区/官方现实

| 来源 | 结论 |
|------|------|
| [ESP-IDF QEMU](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html) | 官方支持 **IDF** 应用；eFuse/安全场景成熟 |
| 社区文 [QEMU 无 WiFi](https://productionesp32.com/posts/internet-in-qemu/) 等 | 网络/外设常缺或需额外打通 |
| [velxio / lcgamboa QEMU](https://github.com/davidmonterocrespo24/velxio) | 浏览器/增强外设；**Arduino-esp32 3.x/IDF5 有已知坑**；非 Grbl 产品现成镜像 |
| Wokwi | 轻量 sketch；Grbl 级 RTOS 运动不可靠 |

### 可行方案

| 方案 | 建议 |
|------|------|
| **保持 out of scope**（推荐） | 用 grblHAL_sim + 真板 G3 覆盖风险；ROI 最高 |
| **旁路实验** | 仅 IDF 小 demo / 安全特性；**不挡** 写字机发布 |
| **远期** | 若迁 FluidNC/IDF 化再评估 QEMU CI |

**结论：没有「社区开箱跑本产品 Arduino Grbl 全栈」的成熟解。**  
不是没搜到，是 **工具边界**；解决方案是 **不把它当门禁**，而不是硬上。

---

## 4. A2A 注册「立刻又 not registered」

### 现象

- `list_agents` / `register_agent` 成功  
- `send_message(..., http://127.0.0.1:4944/)` → `Agent not registered`  
- 磁盘 `registered_agents.json` 键为 **无尾斜杠** URL

### 根因（本机代码）

`resolve_send_target` / `send_message` 用 **字符串全等** 查表；MCP 常传 `...:4944/`，注册存 `...:4944` → 假未注册。  
社区 A2A/MCP 桥（如 [GongRzhe/A2A-MCP-Server](https://github.com/GongRzhe/A2A-MCP-Server)）同样依赖 registry；**URL 规范化**是通用修复。

### 已做修复（mcp-a2a-bridge）

- `a2a_mcp_send_prep.normalize_agent_url` + 注册/加载/发送查表归一  
- 路径：`C:/Users/zhugu/.kimi-code/mcp-a2a-bridge/`
- RESULT 已允许进 git

### 运维方案

1. **重启 MCP a2a-bridge**（用户已 reset 后 `list_agents` 应正常）  
2. `register_agent` 后立刻 `send_message`（URL 有无 `/` 均可）  
3. daemon：`start-a2a-bridge.ps1` 保持 wrapper 健康  

**结论：有解；代码已修，reset 后应可用。**

---

## 建议落地优先级

| 优先级 | 项 | 动作 |
|--------|-----|------|
| P0 | A2A 斜杠 | **重启 a2a-bridge** 验证 register→send |
| P0b | A2A strict 工单 | 用 `a2a_workorders/TEMPLATE.md`（```gates + risk + owns） |
| P1 | G3b 可脚本部分 | **已有** `hil/paper_m30_serial.py`；一键 `scripts/hil_to_gate.py --port` |
| P1b | 全 Win 主机仿真 | **已有** `scripts/win_full_sim.py`（L0–L4；非芯片） |
| P2 | OTA | USB 双版本：`hil_to_gate.py --with-g4`；真 Wi-Fi OTA 仍证据清单 |
| P3 | QEMU | 维持不做产品门禁 |

---

## 参考链接

- Golioth HIL: https://blog.golioth.io/golioth-hil-testing-part1/  
- Golioth board tiers: https://docs.golioth.io/firmware/hardware/  
- pytest-embedded OTA discussion: https://github.com/espressif/pytest-embedded/issues/297  
- ESP-IDF pytest: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/contribute/esp-idf-tests-with-pytest.html  
- Memfault OTA checklist: https://memfault.com/blog/ota-update-checklist-for-embedded-devices/  
- grblHAL Simulator inject: https://github.com/grblHAL/Simulator  
- 本仓：`docs/STATUS.md`、`release/g3_evidence.template.yaml`、`release/g4_ota.template.yaml`
