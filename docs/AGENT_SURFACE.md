# Agent 身上挂的是什么（主机 SIL 装备清单）

一句话：**不是给 agent 再装一个仿真器大脑，而是给它一套「写码前后必跑的体检仪 + 病历 + 禁止胡说的护栏」。**

---

## 1. 类比

| 角色 | 对应 |
|------|------|
| 手术刀 / IDE | 原来就会：读改代码 |
| **体检仪** | `agent_gate`：免真机跑协议/（可选）运动/假绿探测 |
| **病历本** | `agent_observe_last.*`、`triage_last.*`、各类 `*_last.json` |
| **复查单** | `sim_rerun`：只重跑失败项 |
| **出板前签字单** | `release_honesty`：过期绿、禁吹牛 |
| **真机病历（可选）** | `hil_logs` + g3 证据（有板才有） |

Agent **没有**被赋予「数字孪生整机」或「大厂云仿真 API」；被赋予的是 **可重复、可观察、可改进的 PC 验证闭环**。

---

## 2. 分层装备（由内到外）

```text
┌─────────────────────────────────────────────────────────┐
│  纪律（MUST）  AGENTS.md：改运动/协议必须 gate；读 observe │
├─────────────────────────────────────────────────────────┤
│  观察面 R38–R40   agent_observe（绿也写 findings）        │
│  失败面 R34–R35   triage + FAIL SLICES                    │
├─────────────────────────────────────────────────────────┤
│  门禁 agent_gate   case_schema / integrity / protocol /   │
│                    soft_allowlist / (+ hardware on std)   │
├─────────────────────────────────────────────────────────┤
│  引擎 grblHAL_sim  TCP host SIL（≠ 产品 Arduino 全栈）     │
├─────────────────────────────────────────────────────────┤
│  可选 HIL          串口归档 / g3（真机难则 pending_hil）   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 每次 gate 后 agent「身上」多出的固定接口

| 路径 | 何时有 | agent 用来干什么 |
|------|--------|------------------|
| `results/agent_observe_last.md` | **每次** gate | **首选读**：hard/soft/info/optimize + next |
| `results/agent_observe_last.json` | 同上 | 机读；`agent_should_block_done_claim` |
| `results/triage_last.md` | 每次 | 失败用例 send/got 摘要 |
| `results/agent_gate_last.json` | 每次 | 层 pass/fail、hints |
| stdout `AGENT_OBSERVE` | 每次 | 不打开文件也能看到 soft/next |
| stdout `FAIL SLICES` | **仅红** | 立刻看到坏 case |

---

## 4. 能力边界（护栏，不是削弱）

**能发现（免真机）：** 解析错误、模态、缺 F、坏数字、假绿 harness、金样回归、产品 soft 分歧、该跑 standard 却只跑了 quick、无 HIL 证据却想签字。

**不能假装发现：** 纸路机械、按键手感、真 BT 空中、真 Wi‑Fi OTA、电源/射频。这些只能 **HIL 或诚实 pending**。

---

## 5. 标准动作（装备使用说明）

```powershell
cd D:\Users\zhugu\fz
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python scripts/agent_gate.py --profile quick    # 或 standard
# → 读 results/agent_observe_last.md
# → 若 block_done_claim：禁止说 fixed
# → 按 next_actions：sim_rerun / standard / honesty
python scripts/agent_loop.py --profile standard # 自动 gate→observe→rerun
```

---

## 6. 和「大厂接口」的关系

身上挂的是 **本地契约接口**（JSON/MD 报告），不是云仿真 SaaS。  
乐鑫 QEMU / Wokwi 最多是 **旁路探头**，不进默认 hard gate。

---

## 7. 版本锚点

观察面 JSON：`agent_observe` **version 3**（R40）。  
状态总表：`docs/STATUS.md` R12–R40。
