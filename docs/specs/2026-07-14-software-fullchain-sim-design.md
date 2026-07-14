# 免硬件软件全链路仿真设计（非芯片全真）

**版本：** 1.2（2026-07-14 去伪存真 + 高可靠方案）  
**状态：** 方向确认；本版以「多 oracle / 可证伪」为可靠性核心，删除单点仿真幻觉  
**范围：** `D:/Users/Grbl_Esp32` + `D:/QWEN3.0`  
**对外正确称呼：** **软件全链路 SIL + 多源契约回归**（不是 HIL，不是芯片全真孪生）  

**硬件仿真专项（步进/限位/植物/StepOracle）已拆出：**  
→ [`2026-07-14-hardware-sim-optimization-design.md`](./2026-07-14-hardware-sim-optimization-design.md)  
云契约与 FakeDevice 仍以本文为准；**控制器台架优化以硬件仿真 spec 为准。**

---

## 0. 去伪存真（先读）

### 0.1 伪命题（本设计拒绝）

| 伪说法 | 为什么是假的 | 真说法 |
|--------|--------------|--------|
| 「免硬件全真仿真」 | 硅/射频/刷写/机械无法在 PC 等价 | 免硬件 **F0–F2 SIL** |
| 「DeviceTwin 绿了 = 固件 up/down 安全」 | Twin 不是 `.bin`；oracle 可自洽但与物理无关 | Twin 只证 **云↔协议契约** |
| 「grblHAL_sim 绿了 = 本 fork 固件 OK」 | 引擎是 grblHAL，不是 `Grbl_Esp32` 产品树 | L1 只证 **通用 Grbl 协议面** |
| 「QEMU 官方能跑我们的全栈」 | 官方路径是 ESP-IDF；本仓 Arduino+运动+云 | QEMU **不进** 默认门禁 |
| 「有 FakeDevice 就等于全链路」 | QWEN 已有 FakeDevice，但 **未接 gateway 传输、契约极薄** | 必须补 **契约表 + 录包 + 故障注入** |
| 「仿真通过可替代 code review」 | 测试有 **oracle 问题**（错 oracle → 假绿） | 仿真是 **证据层**，review 仍要看变更类 |

### 0.2 真问题（本设计要抓的）

按「发版后能连 + 能跑任务」拆开后，**高可靠且免硬件可抓**的是：

1. **网关/API 契约回归** — 错误码、能力矩阵、拒识、超时语义被改坏  
2. **运动安全边界** — 超工作区、超点数、非法 feed（FakeDevice/safety 已部分覆盖）  
3. **G-code/协议面** — 非法块、`error:N`（grblHAL_sim）  
4. **跨组件集成假设** — consumer 期望的字段/状态与 provider 实现漂移（契约测试解决）  

**免硬件抓不住、却常被当成已测的：**

- 真 `.bin` 启动、NVS、分区、OTA  
- 真 Wi-Fi/BT 链  
- 纸张/I2S/限位物理  
- 「本 fork GCode.cpp 与 grblHAL 行为完全一致」

### 0.3 可靠性第一性原理：多 Oracle

软件测试经典 **oracle problem**：没有独立判据时，仿真只是「自己证明自己」。

**高可靠方案不靠一个更胖的 Twin，而靠多个独立判据同时成立：**

```text
                    ┌─ O1 契约表（错误码/矩阵/schema）     权威：代码+文档钉死
  用例输入 ──► SUT ─┼─ O2 金样回放（lab/prod 录包）       权威：真实历史行为
                    ├─ O3 参考引擎（grblHAL_sim）         权威：上游协议实现
                    ├─ O4 差分/属性（可选）                 权威：双实现一致或不变式
                    └─ O5 故障注入后仍可观测失败           权威：门禁会红
  任一 hard oracle 失败 → 门禁红
  仅 O3 绿而 O1 未跑 → 不得宣称 F2
```

**禁止**把 FakeDevice/Twin 自己的输出当作唯一 oracle（它是 **SUT 的一部分或替身**，不是上帝）。

### 0.4 本仓已有资产（避免重复造轮）

| 资产 | 位置 | 真相 |
|------|------|------|
| `FakeDevice` | `QWEN3.0/tests/helpers/fake_device.py` | 确定性写字机替身；**进程内** command/event，**不是** 网络设备 |
| motion 单测 | `tests/test_device_motion.py` | 安全边界/路径有测 |
| motion_contract | `tests/test_device_gateway_motion_contract.py` | **几乎空壳**（只断言 `E_` 前缀）→ **高可靠缺口 #1** |
| grblHAL + sim_regression | Grbl `tools/` | L1 已可绿；引擎≠本 fork |
| firmware_matrix / MotionErrorCode | `device_gateway/` | 契约原材料已在，**缺强制用例** |

**v1.2 策略：扩展 FakeDevice + 填满契约，而不是另起一个无关 DeviceTwin 神话。**

---

## 1. 外部依据（高可靠相关）

| 来源 | 可借鉴 | 不照搬 |
|------|--------|--------|
| [Pact / CDC](https://docs.pact.io/) 与业界契约测试综述 | Consumer 定义期望；provider 独立验证；契约版本化 | 第一期不必上完整 Pact Broker；可用 **pytest 契约表 + JSON 工件** |
| Record & replay API 回归 | 真实行为固化为可回放工件 | 回放 alone 不够，需契约与负例 |
| 差分测试 / 属性测试实践 | 双实现不一致则至少一方有 bug | 本 fork 无第二完整固件时，差分限 **协议子集 vs grblHAL** |
| ESP-IDF pytest-embedded / host | 官方分层：host / 真板 / qemu | 我们 Arduino 仓：host≈L1/L2；板≈L3；qemu 默认关 |
| Golioth HIL | 真板连网/OTA 才 Continuously Verified | 用户不常插板 → L3 可选且 skip 显式 |
| 乐鑫 QEMU / 知乎 C3 安全文 | 芯片 SIL 有官方位 | 不挡本产品任务链 |
| Gitee | 无免硬件全真 CNC+云 | 不依赖 |
| MathWorks/Ansys HIL 定义 | 纠正术语 | — |

---

## 2. 目标与非目标

### 2.1 高可靠目标（可证伪）

1. **默认门禁可在零 USB 下失败**（破坏注入必红），且失败信息指向契约/金样/协议层。  
2. **每个 hard case ≥2 个独立 oracle 中的一个写死期望**（不是「Twin 说 ok」）。  
3. **契约覆盖率可度量**：`MotionErrorCode` 主码、`firmware_matrix` 相邻版本差、FakeDevice 错误分支。  
4. **证据分级**：报告含 `fidelity`、`oracles_used`、`coverage_gaps`。  
5. **扩展而非替换** QWEN `FakeDevice` 与现有 pytest。

### 2.2 非目标（同前，强调）

芯片全真、纸张物理、OTA 成功率、用 SIL 话术冒充 HIL、单仿真器当唯一真理。

### 2.3 Definition of Done（v1.2 加严）

- [ ] L1 grblHAL regression hard exit 0  
- [ ] L2a：**契约表**覆盖 ≥80% 的 `MotionErrorCode` 成员（每个至少 1 个会失败的用例）  
- [ ] L2a：`firmware_matrix` 至少 2 组「低版本拒识 / 高版本允许」  
- [ ] L2b：金样 ≥10 且每条 `source`∈{lab,prod,replay_derived} 或 schema 否定例  
- [ ] **Fault injection pack** ≥3（超时、断连、执行 error 映射）门禁必红当期望失败时  
- [ ] 报告字段完整（见 §5.2）  
- [ ] `test_device_gateway_motion_contract.py` 不再是空壳  
- [ ] 文档声明：F2 绿 ≠ 发版硅验证  

---

## 3. 高可靠架构（多 oracle）

### 3.1 逻辑视图

```text
                         fullchain_runner (Win/VPS)
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   [L1] Protocol SIL         [L2a] Contracts           [L2b] Replay / FakeDevice
   grblHAL_sim               纯表驱动 pytest            扩展 FakeDevice
   sim_regression            不依赖网络设备              + 可选 TCP 桥接 L1
         │                         │                         │
         │                    O1 契约表                   O2 金样
         │                    (期望 error)                O1 再校验
         └─────────────────────────┴────────── O3 grblHAL ──┘
                                   │
                          report.json (multi-oracle)
                                   │
                    [L3] optional HIL F3 — skip explicit
```

### 3.2 可靠性支柱（按优先级）

| 优先级 | 支柱 | 做什么 | 为何更可靠 |
|--------|------|--------|------------|
| **R1** | **契约表驱动测试** | 把 `MotionErrorCode`/`firmware_matrix`/OpenAPI 变成 **可执行期望** | 期望在表里，不在 Twin 肚子里 |
| **R2** | **金样录包回放** | lab/prod 一次，日常回放 | oracle 来自真实历史 |
| **R3** | **参考协议引擎** | grblHAL_sim 已落地 | 第三方实现，减少「自写自测」 |
| **R4** | **故障注入** | 超时/断连/error 映射 | 证明门禁会红（抗假绿） |
| **R5** | **差分/属性（可选）** | 同输入：安全钳位不变式；或两版 gateway 对比 | 发现回归不靠人工枚举 |
| **R6** | **变异/破坏性抽检（可选）** | 对契约映射函数做突变，看测试是否杀死 | 度量测试套件质量，非常日常 |
| **R7** | **低频 HIL** | test_drive 串口 | 唯一 F3 |

**高可靠日常 = R1+R2+R3+R4。**  
R5–R6 增强；R7 发版托底。

### 3.3 组件映射（去「空 DeviceTwin」叙事）

| 组件 | 实现策略 |
|------|----------|
| 进程内替身 | **扩展** `tests/helpers/fake_device.py`（错误码对齐 `MotionErrorCode` 字符串/枚举） |
| 网关契约 | **重写** `test_device_gateway_motion_contract.py` + 新 `contracts/*.yaml|json` |
| 协议 SIL | 现有 `tools/sim_regression` + `tools/grblhal_sim` |
| 网络级 Twin（若需要） | 仅当 gateway 真实设备通道需要：薄适配层 `FakeDeviceTransport`，内部仍调 FakeDevice |
| 金样 | `device_twin/fixtures/` 或 `tests/fixtures/motion_traces/`（实现时单点路径） |

### 3.4 L1 实操硬约束（社区）

- `grblHAL_sim -n -t 0 -p 7681`  
- 默认 NC → **Alarm**：setup 必须 `$X`  
- 报告 `engine=grblHAL_sim`  
- validator **非** hard gate（Windows 不稳）  
- **差分边界**：不得将 L1 通过解释为 `PaperSystem`/`BTState` 通过  

### 3.5 L2a 契约表（高可靠核心）

建议工件：`QWEN3.0/tests/contracts/motion_error_cases.yaml`

```yaml
# 示例形状（实现可微调）
- id: missing_path_run_path
  capability: run_path
  firmware: v1.2.0
  input: { path: [] }
  expect_error: E_MISSING_PATH   # 或文档规定的等价码
  oracles: [contract_table]
- id: matrix_draw_on_v1_0
  capability: draw_generated
  firmware: v1.0.0
  expect_error: E_UNSUPPORTED_CAPABILITY
  oracles: [contract_table, firmware_matrix]
```

**规则：**

- 契约失败 **不能** 用 FakeDevice「好心改成成功」掩盖  
- FakeDevice 返回的 error 字符串/码必须 **可映射到** 契约枚举（映射表单测）  
- Provider（gateway）与 Consumer（App/任务创建）两侧至少各有一组用例（CDC 思想，轻量实现）

### 3.6 L2b 金样

- 每条 hard 金样标注 `oracles: [trace]`  
- 回放时 **同时** 跑契约再校验（O1∧O2）  
- `synthetic_from_schema` 不得作为唯一成功路径证据  

### 3.7 故障注入包（R4）

| 注入 | 期望 |
|------|------|
| Twin/Fake 停在 ACK 不 DONE | `E_TIMEOUT` 或网关失败态 |
| 中途断开会话 | 可观测失败，无静默 succeeded |
| 路径触发 grblHAL error（若桥接） | `E_EXECUTION_FAILED` + 原因字段 |

无注入套件的「全绿」= **不可信绿**（门禁元测试缺失）。

### 3.8 可选 R5：差分与属性

| 属性 | 描述 |
|------|------|
| 安全钳位 | 超工作区点 → 不越界或 LIMIT 事件（FakeDevice 已有逻辑，升为 property） |
| 矩阵单调 | 高版本能力 ⊇ 声明子集（对 matrix 表结构） |
| 协议差分 | 同一 G-code 子集：grblHAL 与「期望 error 表」一致（不是与未测固件一致） |

### 3.9 L3 HIL

同 v1.1：有板才跑；`skipped_no_board`；禁止 Hardware verified 徽章。

---

## 4. 与「假绿」作战清单

实现与 review 必须对照：

1. ☐ 是否只有 FakeDevice 自测、无契约表？  
2. ☐ 是否缺少失败用例（只有 happy path）？  
3. ☐ 是否把 L1 结果说成本 fork 固件结果？  
4. ☐ L3 skip 是否被写成通过？  
5. ☐ 金样是否无 `source`/日期/固件版本？  
6. ☐ 破坏注入是否存在且 CI 跑过？  
7. ☐ 错误码映射是否单测？  
8. ☐ `motion_contract` 是否仍只有 `startswith("E_")`？  

任一项为是 → **不得**在 PR 写「全链路已验证」。

---

## 5. 门禁与报告

### 5.1 变更 → 证据

| 变更 | 最低 |
|------|------|
| 协议/G-code 通用 | L1 + 相关契约 |
| gateway/错误码/矩阵 | L2a 必绿；相关金样 |
| FakeDevice/安全 | motion 单测 + 契约映射 |
| 发布「可连可跑」 | L1+L2a+L2b + L3 或 defer 工单 |

### 5.2 报告 schema

```json
{
  "sim_mode": "software_fullchain_not_silicon",
  "fidelity": ["F0", "F1", "F2"],
  "oracles_used": ["contract_table", "trace", "grblhal_sim", "fault_injection"],
  "engines": { "L1": "grblHAL_sim", "L2_device": "FakeDevice" },
  "layers": {
    "L1": "pass|fail",
    "L2a": "pass|fail",
    "L2b": "pass|fail",
    "L2_fault": "pass|fail",
    "L3": "pass|fail|skipped_no_board"
  },
  "contract_coverage": { "motion_error_codes": "0.0-1.0", "matrix_pairs": 0 },
  "coverage_gaps": [],
  "cases": []
}
```

### 5.3 Win / VPS

- 默认跑 R1–R4（L1+L2a+L2b+fault）  
- VPS 无 USB → 同左，L3 skip  
- 不在 VPS 上幻想更高芯片保真度  

---

## 6. 分阶段实施（按可靠性收益排序）

| 阶段 | 内容 | 可靠性收益 |
|------|------|------------|
| **P0** | 本 spec；AGENTS 链接 | 对齐预期 |
| **P1** | L1 巩固（已基本完成） | F1 |
| **P2** | **填满契约表 + 重写 motion_contract**（最高 ROI） | 真抓网关/矩阵回归 |
| **P3** | FakeDevice 错误码对齐 + 故障注入包 | 抗假绿 |
| **P4** | 金样录制脚本 + ≥10 回放 | 真实历史 oracle |
| **P5** | 可选 FakeDevice↔grblHAL 桥 | 协议执行面 |
| **P6** | 属性/差分增强 | 降枚举成本 |
| **P7** | 可选 HIL smoke | F3 |
| **P8** | 可选变异抽检契约映射 | 测「测试」 |

**推荐落地顺序：P2 → P3 → P4**（先可靠，再扩 Twin/桥）。  
不先做「宏大 DeviceTwin 平台」。

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| 契约与实现双双写错 | 金样 O2；故障注入；矩阵来自单一 `firmware_matrix` 源 |
| FakeDevice 变第二个错误实现 | 契约优先；禁止 FakeDevice 覆盖 expect_error |
| grblHAL 漂移 | pin submodule；L1 金样 |
| 过度工程 Pact/Broker | 第一期 YAML+pytest；需要跨团队再升级 |
| 无人录金样 | P4 阻塞「F2 完成」宣称 |

---

## 8. 打开问题与默认

| 问题 | 默认 |
|------|------|
| 设备是否已有网络协议 | 先强化 **进程内 FakeDevice+gateway 单测/契约**；网络适配仅在代码证明需要时加 |
| 是否引入 Pact 工具链 | **否**（除非跨 repo 多消费者爆炸） |
| QEMU | 默认不做 |
| 金样存放仓 | 优先 QWEN `tests/fixtures`（靠近 gateway） |

---

## 9. 验收清单（v1.2）

- [ ] 去伪存真 §0 被 AGENTS/README 引用  
- [ ] motion_contract 非空壳，覆盖主错误码  
- [ ] 故障注入包 CI 可见  
- [ ] 多 oracle 报告字段  
- [ ] 无「HIL/全真」误标  
- [ ] FakeDevice 扩展说明写入 QWEN 测试文档  

---

## 10. 参考

- Pact / CDC: https://docs.pact.io/  
- ESP-IDF QEMU: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/tools/qemu.html  
- ESP-IDF pytest: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/contribute/esp-idf-tests-with-pytest.html  
- grblHAL Simulator: https://github.com/grblHAL/Simulator  
- Golioth HIL: https://blog.golioth.io/golioth-hil-testing-part1/  
- MathWorks HIL: https://ww2.mathworks.cn/discovery/hardware-in-the-loop-hil.html  
- 知乎 QEMU 安全向: https://zhuanlan.zhihu.com/p/694239198  
- 本仓：`tools/sim_regression/`、`tools/grblhal_sim/`  
- QWEN：`tests/helpers/fake_device.py`、`tests/test_device_gateway_motion_contract.py`、`device_gateway/protocol_families.py`、`firmware_matrix.py`  

---

## 11. 一句话

**高可靠 = 多独立 oracle（契约 + 金样 + 参考协议引擎 + 故障注入）+ 诚实保真度；  
不是更大的单一仿真器，也不是免硬件全真。**
