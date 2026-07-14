# 硬件仿真优化设计（控制器 / 虚拟机床 / 可选真硅）

**版本：** 1.0（2026-07-14）  
**状态：** 响应「主要还是硬件仿真的优化改进」——与云契约全链路解耦，专攻 **运动控制器仿真保真与可测性**  
**关联：** 软件全链路 SIL 见 `2026-07-14-software-fullchain-sim-design.md`（F2 云任务）；**本文 = F1 协议机 + 虚拟 I/O 植物 + F3 可选**  
**非目标：** ESP32 芯片全真 QEMU 跑本 Arduino 产品固件；纸张/机械 FEA。

---

## 0. 去伪存真：什么叫「硬件仿真」

| 层级 | 名称 | 有没有「硬件味」 | 本仓主优化对象 |
|------|------|------------------|----------------|
| **H-SIM-A** | 主机控制器仿真 | 真规划器/步进逻辑在 PC（grblHAL_sim） | **是（主）** |
| **H-SIM-B** | 虚拟机床 / I/O 植物 | 限位、探针、门、急停、行程模型 | **是（主）** |
| **H-SIM-C** | 步进轨迹 oracle | step/block 日志 → 位置/速度检查 | **是（主）** |
| **H-SIM-D** | 芯片仿真 QEMU | 真 ISA，假外设 | **否（旁路）** |
| **H-SIM-E** | 真硅无电机 | `test_drive` 真 ESP32 | **可选增强，非常驻** |

社区/官方依据：

- [grblHAL/Simulator](https://github.com/grblHAL/Simulator)：外设用 struct 模拟；可输出 **step/block**；`-p` TCP；stdin 可触发 hold/限位等；**approximate realtime**  
- ioSender / Sienci：无板用 sim 测 sender  
- Grbl_Esp32 `test_drive`：真板、无 pin、无电机  
- 乐鑫 QEMU：芯片级，**Wi‑Fi 等弱**；不适合当 CNC 步进主路径  
- 工业「test without motor」：驱动器侧无电机联调——对标 **H-SIM-A/E**，不是全机械孪生  

**优化目标一句话：**  
在 **不常插板** 前提下，把 H-SIM-A/B/C 做到 **可脚本、可回归、可抓真实运动/协议/I/O 类问题**；需要时再接 H-SIM-E。

---

## 1. 现状与缺口

### 1.1 已有

| 资产 | 能力 | 缺口 |
|------|------|------|
| `tools/grblhal_sim/bin/grblHAL_sim.exe` | TCP 协议、规划执行 | 未系统用 `-s/-b` 步进日志 |
| `tools/sim_regression/` | ok/error 用例 | 几乎不测限位/探针/软限位/步进计数 |
| `test_drive.h` | 真板无 I/O | 无自动化串口 plant |
| 产品机 `custom_3axis_hr4988` / 纸张 | 真硬件 | **无** 对应虚拟植物 |

### 1.2 要抓的「硬件向」真实问题（仿真可逼近）

| 问题类 | H-SIM 能否逼近 | 手段 |
|--------|----------------|------|
| 非法 G-code / 模态 | 高 | 现有 L1 |
| 软限位 / 超程 | 中高 | 设行程 + 越界 G0 |
| 限位触发 → Alarm | 中 | 注入 limit 事件（sim stdin/API） |
| 探针周期 | 中 | 注入 probe |
| 加减速/规划异常 | 中 | block.out / block 分析 |
| Feed hold / 恢复 | 中 | 实时字符注入 |
| 本 fork 纸张时序 | 低 | 需产品逻辑 mock 或真机 |
| I2S 74HC595 时序 | 极低 | 真机或专用 mock |
| 刷写/Wi-Fi PHY | 极低 | 真机 |

---

## 2. 优化原则

1. **吃干官方 sim 能力**，再写薄封装；不 fork 重写 grblHAL core。  
2. **植物（plant）与控制器分离**：控制器 = grblHAL_sim；植物 = 我们的脚本（限位几何、探针触发时刻）。  
3. **oracle 可计算**：步进数 × 脉冲当量 → 期望位置；与 `?` 报告 MPos 交叉验证。  
4. **时间模型显式**：`-t 0`（尽快）用于 CI；`-t 1` 用于实时交互；禁止混用未标注。  
5. **产品分叉隔离**：纸张/BT 进 **ProductPlant stub**（显式 gap），不假装 grblHAL 已覆盖。  
6. **与云契约解耦**：本文不解决 QWEN dispatch；只提供 **硬件侧可调用的可靠端点**（TCP sim + 报告）。

---

## 3. 目标架构

```text
                    ┌──────────────────────────────────────┐
                    │   hardware_sim_runner (Python)         │
                    │   tools/hardware_sim/                  │
                    └──────────────────────────────────────┘
                       │              │                │
                       ▼              ▼                ▼
              grblHAL_sim      PlantController    StepOracle
              -n -t 0|-t 1     limits/probe/door   parse step.out
              -p PORT          soft travel model   vs MPos / G-code
              -s step.log
              -b block.log
                       │
                       ▼
              cases/hardware/*.json
              (motion + inject + expect)
                       │
         optional ─────┴──── serial to real ESP32 test_drive
```

### 3.1 模块

| 模块 | 路径（建议） | 职责 |
|------|----------------|------|
| Runner | `tools/hardware_sim/run_hw_sim.py` | 启停 sim、跑用例、汇总 |
| Client | 可复用 `sim_regression` 的 TCP client | 发 G-code / 实时字节 |
| Plant | `tools/hardware_sim/plant.py` | 按脚本注入 limit/probe/hold；软限位期望 |
| StepOracle | `tools/hardware_sim/step_oracle.py` | 解析 `-s` 步进日志，积分位置 |
| Cases | `tools/hardware_sim/cases/` | 硬件向用例 |
| Product stubs | `tools/hardware_sim/product_stubs.md` | 纸张/BT 未仿真清单 |

### 3.2 用例 schema（硬件向）

```json
{
  "id": "soft_limit_trip_x",
  "time_factor": 0,
  "setup": ["$X", "G21", "G90", "$20=1"],
  "steps": [
    { "send": "G0 X9999", "expect": "error_or_alarm", "codes_any": ["ALARM", "error"] }
  ],
  "inject": [],
  "step_log": false,
  "notes": "depends on settings; pin expected codes after first lab pass"
}
```

注入示例（待对接 sim 实际 stdin 协议后钉死）：

```json
{
  "id": "limit_inject_while_move",
  "steps": [
    { "send": "G1 X50 F1000", "async": true },
    { "inject": "limit_x_pos", "after_ms": 50 },
    { "expect_status": "Alarm" }
  ]
}
```

---

## 4. 优化工作包（按 ROI）

### WP-H1 — 吃干 grblHAL 观测面（最高 ROI）

**做什么：**

- Runner 支持：  
  - `-s tools/hardware_sim/results/step_<id>.log`  
  - `-b tools/hardware_sim/results/block_<id>.log`  
  - `-e` 独立 EEPROM 文件（避免用例串设置）  
- 用例结束后归档日志；失败时保留。  
- 文档化官方能力（step 可视化、规划波动）——来自 Simulator README。

**验收：** 任意 pass 运动用例可生成非空 step 日志；CI 可选上传 artifact。

### WP-H2 — StepOracle（步进 → 位置）

**做什么：**

- 解析 step 日志格式（实现时以实际文件为准，写 golden parser 测试）。  
- 配置 `steps_per_mm`（与 `$100` 等一致，用例内声明）。  
- 断言：积分位置与最终 `MPos` 误差 &lt; ε（如 0.02mm）。  
- 可选：最大步进率峰值报告（性能回归）。

**验收：** `G1 X10` 类用例 oracle 绿；故意改 steps_per_mm 则红。

### WP-H3 — 虚拟 I/O 植物（限位 / 探针 / 门 / Hold）

**做什么：**

- 查清并文档化 grblHAL_sim **stdin 硬件事件** 字符/命令（官方：feed hold、cycle start、limit set/clear）。  
- `Plant` 封装：`assert_limit`, `pulse_probe`, `open_door`, `feed_hold`.  
- 用例：运动中触发限位 → Alarm；探针 G38 类（若 sim 支持）。  
- **Alarm 默认态**：全局 setup `$X`；文档 NC 开关陷阱（grblHAL 社区）。

**验收：** ≥3 注入类 hard 用例稳定；无真板。

### WP-H4 — 软限位 / 工作区模型

**做什么：**

- 用例固定 `$130/$131/$132` 行程与 `$20` 软限位。  
- 越界运动期望 error/alarm（以 sim 实测码钉死，写入 cases）。  
- 与 QWEN `DEFAULT_WORKSPACE_MM` **对照表**（允许数值不同，但要有映射说明，避免云/机行程各说各话）。

**验收：** 越界必红；界内短路径必绿。

### WP-H5 — 时间模型与稳定性

**做什么：**

- CI 默认 `-t 0`；交互 profile `-t 1`。  
- 超时策略：运动行 wait 与 time_factor 联动。  
- Windows：独立 `EEPROM_<case>.DAT`；杀残留端口进程。  
- 锁定 `src_repo` submodule 版本；升级 sim 必须重跑 WP-H2/H3。

**验收：** 连续 20 次 full hardware_sim 无 flake（本机基线）。

### WP-H6 — 与 sim_regression 合并入口

**做什么：**

- `run_hw_sim.py --include-protocol` 可调用现有 pass/fail。  
- 或 `run_regression.py --hardware-suite` 扩展；**避免两套 client 分叉**——抽公共 `grbl_tcp.py`。

**验收：** 一键 `python tools/hardware_sim/run_hw_sim.py --start-sim` exit 0。

### WP-H7 — 产品植物 Stub（诚实 gap）

**做什么：**

- `product_stubs.md` 列出：纸张换纸、BT 状态机、I2S 扩展、自定义 M 码。  
- 每个 stub：`status=unsimulated` + 建议真机用例 ID。  
- **禁止** 用 grblHAL 绿勾选这些项。

### WP-H8 — 可选真硅无电机（H-SIM-E）

**做什么：**

- `run_hw_sim.py --backend serial --port COMx`  
- 仅 `test_drive` 配置：boot、`$I`、短 G0、无 step 日志则跳过 StepOracle。  
- 无串口 → `skipped_no_board`。

**验收：** 有板时与 TCP 用例子集对齐（协议层）。

### WP-H9 — 明确不做（防范围爆炸）

| 项 | 原因 |
|----|------|
| 本 fork 全量进 QEMU | Arduino 全栈 + 外设缺失；ROI 低 |
| 仿真 I2S 位时序 | 无现成模型 |
| 机械动力学 / 抖动 FEA | 超范围 |
| 在 sim 内重写 PaperSystem | 应抽纯逻辑单测或真机，不塞进 grblHAL |

---

## 5. 与「软件全链路」spec 的分工

| 关注点 | 硬件仿真 spec（本文） | 软件全链路 spec |
|--------|----------------------|-----------------|
| grbl 协议 / 步进 / 限位 | **主场** | 仅 L1 调用 |
| QWEN 契约 / FakeDevice | 不负责 | **主场** |
| 多 oracle 哲学 | StepOracle + 注入 + error 码 | 契约 + 金样 + fault |
| 日常零 USB | TCP sim | TCP + FakeDevice |
| 发版硅 | WP-H8 可选 | L3 可选 |

**集成点：** fullchain 的 L1 应逐步切换到 `hardware_sim` 报告（含 step oracle），而不是两套互斥。

---

## 6. 成功标准（硬件仿真优化完成）

- [ ] 公共 TCP client 无分叉  
- [ ] step 日志 + StepOracle 至少 5 个运动用例  
- [ ] I/O 注入至少 3 个稳定用例  
- [ ] 软限位/行程至少 2 个用例  
- [ ] 一键 runner；结果 JSON 含 `sim_engine=grblHAL_sim`、`time_factor`、`plant_events`  
- [ ] product_stubs 清单存在且 review 检查单引用  
- [ ] 文档写明 approximate realtime 与非本 fork 二进制  

---

## 7. 实施顺序（建议）

```text
WP-H6 抽公共 client（小）
  → WP-H1 日志全开
  → WP-H2 StepOracle
  → WP-H5 稳定与 EEPROM 隔离
  → WP-H4 软限位
  → WP-H3 注入植物（依赖事件协议摸清）
  → WP-H7 stubs 文档
  → WP-H8 可选 serial
```

**WP-H3 摸清 stdin 协议** 是唯一可能卡住点：实现前用官方文档 + 实验脚本探测，写入 `tools/hardware_sim/docs/sim_inject_protocol.md`。

---

## 8. 风险

| 风险 | 缓解 |
|------|------|
| step 日志格式变更 | parser 单测 + pin sim 版本 |
| 注入协议未文档化 | 探测脚本；不支持则 H3 降级为「仅软限位」 |
| 与本 fork 行为差 | 报告 engine 字段；产品项走 stubs |
| flake | `-t 0` + 隔离 EEPROM + 端口清理 |
| 范围滑向 QEMU | WP-H9 硬拒绝 |

---

## 9. 参考

- grblHAL Simulator README：step/block、TCP、approximate realtime  
- https://github.com/grblHAL/Simulator  
- ioSender sim 联调说明  
- Sienci：gSender + simulator  
- Grbl_Esp32 `Machines/test_drive.h`  
- ESP-IDF QEMU（旁路）：https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html  
- 本仓：`tools/sim_regression/`、`tools/grblhal_sim/`  

---

## 10. 一句话

**硬件仿真优化 = 把 grblHAL_sim 从「会回 ok/error」升级到「可注入 I/O + 可校验步进轨迹 + 可隔离设置」的虚拟控制器台架；  
不是芯片全真，也不是再写一套云 FakeDevice。**
