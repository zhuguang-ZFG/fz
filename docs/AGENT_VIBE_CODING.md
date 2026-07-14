# Agent vibe coding：PC 仿真优先（少烧录）

**目标：** 让 AI agent **必须主动**在电脑上跑门禁，先抓解析/运动/协议问题，再考虑烧录。

**HARD RULE（三仓一致）：**  
- `Grbl_Esp32/AGENTS.md` · `QWEN3.0/AGENTS.md` §硬规则 7 · `fz/AGENTS.md`  
- 改运动/G-code/协议相关 → **自己跑 gate**，禁止等用户催、禁止只烧录排 parser。

**入口（唯一推荐）：**

```powershell
cd D:\Users\zhugu\fz
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python scripts/agent_gate.py
```

报告（固定路径，方便 agent 解析）：

`D:\Users\zhugu\fz\results\agent_gate_last.json`

---

## Agent 必须遵守的调用纪律

### 何时必须跑（主动，不等人说「测一下」）

| 改了什么 | 最低 profile |
|----------|----------------|
| `GCode` / `Protocol` / `Serial` / 设置解析 | `quick` 或 `auto` |
| `Planner` / `Stepper` / `MotionControl` / `Limits` / `Jog` | `standard` |
| `Custom/paper*` / `BTState` / 纸路相关 | `standard` + 声明 **HIL 仍缺** |
| `fz` 的 `protocol_sim` / `hardware_sim` / `sim_common` | `standard` |
| 准备说「修完了 / 可以烧录验证运动」 | **至少 `standard` 绿** |
| 发版前 | `deep` 或 `full_release_smoke` + 真机证据 |

### 何时可以不跑

- 纯 Markdown/注释、与运动无关的文案  
- 纯 Web UI 静态资源且不碰固件协议  

### 失败时

1. 读 `results/agent_gate_last.json` → `failures` + `agent_hints`  
2. **只重跑失败用例（快）：**  
   ```powershell
   python scripts/sim_rerun.py --from-last
   python scripts/sim_rerun.py --list
   python scripts/sim_rerun.py --protocol undefined_feed --hardware move_x_10
   ```  
3. soft 分歧（产品样本 vs grblHAL，不硬红）：`protocol_sim/results/soft_divergence.json`  
4. 金样 / 假绿探测：`protocol_sim/results/golden_last.json`、`integrity_inject_last.json`  
5. **不要**为了「看串口」去烧录排 parser/error 类问题  

```powershell
# R19 单独重跑
python protocol_sim/run_regression.py --start-sim --golden
python protocol_sim/run_regression.py --start-sim --integrity-inject
python -m unittest scripts.test_gate_integrity -v
# R23 从 last_report / fail JSON 录金样（默认不覆盖手写 golden）
python scripts/golden_record.py --from-last --kinds fail --only undefined_feed --dry-run
python scripts/golden_record.py --from-case protocol_sim/cases/fail/bad_number.json
# R24 soft 高分歧是否在允许名单
python scripts/soft_allowlist.py
```

### 绿了也不要说的话

- 「纸路/BT/OTA 已验证」— 需要 `hil_to_gate` + g3/g4  
- 「本 fork 与 grblHAL 行为完全一致」  
- 「QEMU 产品全栈 OK」  
- 「已按 `idf.py simulate` 无硬件验完全固件」— 官方路径是 `idf.py qemu` / host-apps；**产品主路径是 agent_gate**。详见 `docs/specs/2026-07-14-community-esp-sim-vs-official.md`  


---

## Profile 说明

| profile | 内容 | 约时 |
|---------|------|------|
| `auto` | 看 git 变更启发式 | — |
| `quick` | protocol + sim_common 单测（R21：integrity/protocol **共用** 一个 sim） | ~40–90s |
| `standard` | + hardware_sim（默认 vibe；hw 仍单独起 sim） | ~1–2min |
| `deep` | + full_release_smoke | ~2–3min |
| `firmware` | + pio `test_drive` G0 | 长 |

```powershell
python scripts/agent_gate.py --profile quick
python scripts/agent_gate.py --profile standard
python scripts/agent_gate.py --profile deep
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python scripts/agent_gate.py --profile firmware
# R21 调试：每层各自 --start-sim
python scripts/agent_gate.py --profile quick --no-shared-sim
```

CI（R22/R26）：`.github/workflows/host_sil.yml` — push/PR 跑 `quick`；schedule/dispatch `run_standard` 跑 `standard`。
R27：`release_honesty.py --require-agent-gate` 默认 `--max-age-hours 24`（发版用 `--max-age-hours 168`）。

### 闭环加速（类「改网表 → 再跑 ERC」）

```powershell
# 一键：gate → 失败则 sim_rerun → 再 gate
python scripts/agent_loop.py --profile standard
python scripts/agent_loop.py --profile quick --honesty   # 末尾附发版诚实度（HIL 可 pending）
```

### 发版诚实度（类「出板前 DRC 汇总」，非下单）

```powershell
python scripts/release_honesty.py --require-agent-gate --allow-pending-hil
# 真要签字（scope 含纸路/OTA 时必须证据）：
python scripts/release_honesty.py --require-agent-gate `
  --scope release/scopes/pre-release-min.yaml
# 报告: results/release_honesty_last.json
```

对照说明：`docs/specs/2026-07-14-eda-inspired-release-honesty.md`（KiCad/立创分流启发）

打印合同：

```powershell
python scripts/agent_gate.py --print-contract
```

---

## 与产品仓协作

固件仓 **不要**再堆 sim 源码。`Grbl_Esp32/AGENTS.md` 指向本仓。

固件仓一键（可选）：

```powershell
# Grbl_Esp32/tools/agent_gate.ps1  → 调 FZ_ROOT
$env:FZ_ROOT='D:\Users\zhugu\fz'
.\tools\agent_gate.ps1
```

---

## A2A 工单

工单 ````gates` 建议写：

```gates
cd D:/Users/zhugu/fz
python scripts/agent_gate.py --profile standard
# expect: 0
# report: results/agent_gate_last.json
```
