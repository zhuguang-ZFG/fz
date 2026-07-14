# A2A 增强：仿真建设与上线挖缺工作流设计

**版本：** 1.0（2026-07-14）  
**仓库：** [zhuguang-ZFG/fz](https://github.com/zhuguang-ZFG/fz)  
**目的：** 在设计/实现仿真台架与 **上线前固件缺陷门禁** 时，用现有 **A2A 舰队** 提高吞吐与可靠性；**不**用 agent 口述替代 `release_gate` 机器证据。

**对齐（本机 Kimi AGENTS 纪律）：**

- 标准链路：**Kimi 定 risk/工单 → 实现 → 机械门禁绿 → Atom 初审 → [med|high] Claude 交叉 → Kimi 终审落地**  
- 角色：Reasonix=编码牛马；Atom=审核牛马；Claude=重活+交叉；Kimi=方案/risk/终审  
- 工单：长文写入文件，A2A 消息只发短指针  
- 详见：`C:/Users/zhugu/.kimi-code/AGENTS.md` A2A 章节；`mcp-a2a-bridge/docs/risk_routing.md`（若存在）

**关联：**

- [pre-release defect gate](./2026-07-14-pre-release-firmware-defect-gate-design.md)  
- [hardware-sim optimization](./2026-07-14-hardware-sim-optimization-design.md)  
- [software fullchain SIL](./2026-07-14-software-fullchain-sim-design.md)  

---

## 0. 去伪存真

| 伪 | 真 |
|----|-----|
| 多 agent 并行 = 更可靠 | 无门禁时并行只放大错误；**可靠 = gate 绿 + 双审** |
| Atom/Claude 说 LGTM = 可上线 | 仅代码意见；上线看 **G0–G5 bundle** |
| 把整仓丢给 Reasonix | 工单必须可验收、可机测；长文文件指针 |
| A2A 跑真机 HIL | 默认 **不**；HIL 由本机/实验室脚本，agent 最多写脚本 |

---

## 1. 为何 A2A 适合本目标

**核心目标：** 上线前挖净 **发布范围内** 固件问题。

| 痛点 | A2A 增益 |
|------|----------|
| 台架/用例/契约面广 | Reasonix **并行** 开工单（多 cases、多 gate 脚本） |
| 假绿/静默错误 | Atom **狂审** + med/high Claude **交叉** |
| 风险不均 | **risk=low\|med\|high** 路由，安全/纸路/BT 走 high |
| 主控上下文爆炸 | 工单文件 + 短指针；Kimi 只收 **gate 输出与 review 摘要** |

效率：能并行就并行（多 fail case、多 WP-H*）。  
可靠：实现后 **必须** 本机/CI 重跑机械门禁，**禁止**采信「agent 说测过了」。

---

## 2. 角色 × 门禁层

| 角色 | 做什么 | 不做什么 |
|------|--------|----------|
| **Kimi（主控）** | 拆 risk、写/审工单路径、跑/验收 `release_gate` 与 protocol_sim、合并决策、签字材料 | 不把 Blocker 伪造成 waiver |
| **Reasonix** | 实现 fz 脚本/用例/plant/StepOracle；扩 QWEN 契约测试；写 HIL 串口脚本 | 不改发布 scope 撒谎；不跳过 fail |
| **Atom** | 门禁绿后 diff 初审：假绿、路径错误、缺负例、taxonomy 覆盖 | 不替代 G3 真机 |
| **Claude** | risk≥med 实现或交叉：纸路交互、BT 流控、安全、门禁编排正确性 | 不替代 Kimi 终审重跑 gate |
| **Codex** | 渠道稳时分流 low 实现 | 不稳则让 Reasonix |

**硬顺序（与全局 A2A 一致）：**

```text
实现(A2A) → 机械门禁绿(本机 Kimi 重跑) → Atom → (med|high) Claude → Kimi 终审
未绿不进审；high 不跳过 Claude。
```

---

## 3. 风险定级（仿真 / 门禁 / 固件）

### 3.1 四问（辅助）

1. 验收是否机器可查？  
2. 是否只改测试/文档？  
3. 失败是否仅本地、无上线误判？  
4. 返工是否廉价？  

全是且无安全/产品运动 → 可 **low**；任一否 → **≥med**。

### 3.2 与缺陷 taxonomy / 工作包映射

| 工作项 | 默认 risk | 实现 | 初审 | Claude 交叉 |
|--------|-----------|------|------|-------------|
| protocol 新 fail case、文案、scope 模板 | **low** | Reasonix | Atom | 关 |
| `release_gate.py` 编排、G0 调 pio | **med** | Reasonix | Atom | **开** |
| hardware_sim StepOracle / 软限位 | **med** | Reasonix | Atom | **开** |
| I/O 注入植物、Alarm 语义 | **med** | Reasonix | Atom | **开** |
| 映射 ACCEPTANCE 纸路/BT 到 G3b 自动化 | **high** | Claude 或 R+必交叉 | Atom | **必开** |
| 安全 G5、鉴权、OTA 门禁 | **high** | Claude | Atom | **必开** |
| QWEN 契约填满（错误码/矩阵） | **med** | Reasonix | Atom | **开** |
| 产品固件 `paper_system`/`Protocol` 修复 | **high** | Claude 优先 | Atom | **必开** |

---

## 4. 工单形态（防截断、可验收）

### 4.1 文件位置

```text
fz/a2a_workorders/<date>_<topic>.md     # 推荐：工单住在 fz
# 或 C:/Users/zhugu/a2a_workorder_<topic>.md  # 全局纪律兼容
```

A2A 消息仅：

```text
risk: med
读取 D:/Users/zhugu/fz/a2a_workorders/2026-07-14_step_oracle.md 并照单执行。
完成后在同目录写 RESULT.md（命令、exit code、日志路径）。
```

### 4.2 工单必含字段

```markdown
# 工单标题
risk: low|med|high
repo: fz|Grbl_Esp32|QWEN3.0
paths: 允许修改的路径列表
goal: 一句话
acceptance:
  - 机器命令: `python ...` 期望 exit 0
  - 禁止: 无负例、跳过 fail、改 scope 藏问题
out_of_scope:
  - ...
gate_touch: G0|G1|G2|G3|G4|G5|none
taxonomy: D2,D3,...
```

### 4.3 完成物

- 代码/用例 diff  
- `RESULT.md`：真实命令与 exit code（**禁止**「应该过了」）  
- 若动门禁：附 `protocol_sim/results/` 或未来 `release/bundles/` 片段  

Kimi **亲自重跑** acceptance 命令，不采信 RESULT 转述（全局纪律）。

---

## 5. 并行拆分模式（效率）

在 **无共享可变状态** 时可并行 Reasonix：

| 并行槽 | 示例工单 |
|--------|----------|
| A | protocol_sim 新 fail 用例集 |
| B | hardware_sim StepOracle parser + 单测 |
| C | release_gate G0 调用骨架 |
| D | QWEN motion_contract 填码表（QWEN_ROOT） |

**禁止并行：** 两人同时改 `release_gate.py` 同一文件；同时改产品 `paper_system.cpp`。  
合并后：**单线程** 跑全量相关 gate。

Atom 可对 **多 PR/多目录** 并行初审（读 only）。

---

## 6. 与 release_gate 的咬合

```text
开发迭代（A2A 加速）
  Reasonix 实现 WP / case
       │
       ▼
  Kimi: python protocol_sim/... 或 release_gate --only G0,G1
       │ fail → 打回工单，不进 Atom
       ▼ pass
  Atom 初审（假绿、缺负例、taxonomy）
       │
       ▼ med/high
  Claude 交叉
       │
       ▼
  Kimi 终审 + 更新 design/checklist 指针

预发布冻结
  Kimi 主持完整 G0–G5（可派 Reasonix 修红，不可派「代签字」）
  G3b 真机：人类或实验室；A2A 只允许准备脚本与记录模板
  SIGN_OFF：人类
```

**A2A 永不拥有：** `SIGN_OFF.md` 签字、`executive_waive` 批准、把 Unknown 标成 pass。

---

## 7. 可靠性专用 A2A 检查单（Atom/Claude）

审仿真/门禁 diff 时固定四刀：

1. **会红吗？** 是否有故意失败用例？故障注入？  
2. **oracle 独立吗？** 是否只有 FakeDevice/自洽？  
3. **引擎诚实吗？** 是否把 grblHAL 说成产品固件？  
4. **scope 一致吗？** `features.paper_path` 是否无 G3b 证据？  

任一项存疑 → **request changes**，不得 LGTM。

---

## 8. 通道与安全（简要）

- 工单与 RESULT 可含路径，**禁止** 塞密钥、session、`.env`  
- A2A 通知（TG/微信）只报 gate 红绿摘要，不当遥控改 scope  
- workdir 落在 `FZ_ROOT` / `GRBL_ROOT` / `QWEN_ROOT` 白名单内  

---

## 9. 落地清单（fz）

| 项 | 说明 |
|----|------|
| `a2a_workorders/` | 工单与 RESULT，gitignore 可选保留模板 |
| `a2a_workorders/TEMPLATE.md` | 标准字段 |
| `docs/specs/` 本文件 | 流程权威 |
| pre-release design 交叉引用 | 已链到 A2A |
| 首批可派工单 | 见 §10 |

---

## 10. 建议首批 A2A 工单（示例标题）

1. **low** — 增加 protocol_sim 软限位相关 fail/pass 草案（先文档码，再钉实测码）  
2. **med** — `scripts/release_gate.py` 最小骨架：调 G1 protocol_sim + 写 SUMMARY  
3. **med** — hardware_sim：公共 TCP client 从 protocol_sim 抽出  
4. **med** — QWEN：填满 `test_device_gateway_motion_contract` 主错误码  
5. **high** — G3b 电子化：ACCEPTANCE 表 → YAML + 人工勾选导入 bundle  

Kimi 按 risk 路由派发；每单 acceptance 必须可机器或半自动验证。

---

## 11. 一句话

**A2A 用来并行实现与双重审查；上线可靠性仍只认 release_gate 证据包与人类签字。**  
设计阶段即按 risk 拆工单，实现阶段禁止未绿进审，预发布禁止 agent 代签。
