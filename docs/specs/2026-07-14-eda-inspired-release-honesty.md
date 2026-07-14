# EDA 开源实践启发：闭环速度与发版诚实度

**版本：** 1.0（2026-07-14）  
**对照：** KiCad（开源 EDA）、立创 EDA / EasyEDA（设计→仿真→下单分流）、LibrePCB 等  
**落点：** `fz` 仿真台架 + 发版门禁（不是抄 UI）

---

## 1. 他们在防什么（和我们同构）

| EDA 习惯 | 防的假绿 | 我们对应 |
|----------|----------|----------|
| **ERC**（原理图电气规则） | 未连接网络、电源脚悬空就画 PCB | **SIL hard**（`agent_gate` / protocol） |
| **DRC**（PCB 设计规则） | 间距/钻孔不过就出 Gerber | **SIL motion + 可选编译 G0** |
| **Plot / 下单前检查** | 未过 DRC 就去嘉立创 | **`release_honesty` + SIGN_OFF** |
| **SPICE 仿真**（EasyEDA 等） | 电路瞬态；**不等于**可制造 | **grblHAL_sim / QEMU 实验** |
| **DFM / 工厂审单** | 制造约束 | **HIL g3/g4 证据**（真机） |
| **QA 单测 vs 发版** | 单测绿 ≠ 用户可装包 | soft 分歧 ≠ 产品签字 |

KiCad 社区长期强调：**规则检查可机跑、可重复**；发版/出板是 **另一道门**，不能用「我仿真过了」代替 DRC。  
立创/EasyEDA：**仿真与下单流程分离**——和我们「agent_gate 与 hil_to_gate 分离」一致。

---

## 2. 可抄的纪律（不抄百万行 C++）

1. **默认机检** — ERC/DRC 风格：合并/宣称完成前必须有 artifact。  
2. **错误分级** — Error 挡发版；Warning/soft 记账（soft_divergence）。  
3. **出板清单** — Gerber 前 checklist → 我们的 `SIGN_OFF` + honesty JSON。  
4. **禁止静默跳过** — 未测 = Unknown → Blocker 或书面 waive（与 KiCad「acknowledge」同类）。  
5. **快闭环** — 改一处规则只重跑相关检查 → `sim_rerun --only`。

**不抄：** 重型 GUI、全板 SPICE 当产品验收、用仿真代替工厂审单。

---

## 3. 本仓落地命令

```powershell
# 开发闭环（类 ERC，快）
python scripts/agent_gate.py --profile quick|standard
python scripts/sim_rerun.py --from-last

# 发版诚实度（类「出板前 DRC 汇总」）
python scripts/release_honesty.py
python scripts/release_honesty.py --require-agent-gate --max-age-hours 72
```

---

## 4. 诚实度输出

`results/release_honesty_last.json`：

- `sil_status` / `agent_gate_age_h`
- `soft_high_divergence[]`
- `hil_required` vs `hil_present`（g3/g4 路径）
- `forbidden_claims_hit[]`
- `verdict`: `ready_for_dev` | `ready_to_sign_pending_hil` | `blocked`

---

## 5. 参考

- KiCad：规则检查与制造输出分离（论坛/QA 传统：DRC 可脚本化诉求）  
- [EasyEDA Simulation docs](https://github.com/dillonHe/EasyEDA-Documents/blob/master/Tutorial/Simulation.md)（ngspice 与设计流分离）  
- LibrePCB：构建/测试与发布文档分流  
- 本仓：`RESIDUAL_GAPS_SOLUTIONS.md`、`AGENT_VIBE_CODING.md`
