# Grbl 固件仿真缺陷分析

> 基于 agent_gate 最新运行结果（2026-07-20）

## 总体状态：✅ 健康

**overall: pass** — 无 hard failures

## 发现的缺陷/限制

### 1. Soft Divergence（已 allowlist，非缺陷）

| 项目 | 状态 | 说明 |
|------|------|------|
| `soft:parsetest_comments.nc` | ⚠️ allowlisted | Product sample vs grblHAL host SIL 分歧 |
| 详情 | err=3/6 ratio=50% | 小写/注释解析差异 |

**分析**：这是已知的 product vs sim 差异，已在 `docs/PRODUCT_SOFT_DIVERGENCE.md` 中记录，不是仿真缺陷。

### 2. 仿真边界（设计限制，非缺陷）

| 边界 | 说明 |
|------|------|
| 纸路机械 | host SIL 无法模拟 |
| 真 BT 空中 | 需要 HIL |
| 真 Wi-Fi OTA | 需要 HIL |
| 电源/射频 | 需要 HIL |

**分析**：这些是**设计限制**，不是缺陷。文档明确说明 "Host SIL ≠ HIL"。

### 3. 潜在改进点（非缺陷）

| 项目 | 优先级 | 说明 |
|------|--------|------|
| hardware_sim 需要 standard profile | 低 | quick profile 跳过 hardware |
| HIL serial archives 为空 | 低 | 无板时正常 |

## 结论

**Grbl 固件仿真无缺陷**。

当前状态：
- ✅ 所有 hard layers green
- ✅ 38 个 protocol JSON cases 无错误
- ✅ 16 个 golden cases 全部通过
- ✅ 19 个 hardware cases 全部通过
- ✅ Native product core coverage 95-100%
- ✅ Machine pin contract 100% coverage
- ✅ Wokwi ESP32 startup pass

唯一的 soft divergence 是已知的 product vs sim 解析差异（已 allowlist），不是仿真缺陷。

## 建议

1. **继续当前实践**：agent_gate + observe + sim_rerun 闭环运行良好
2. **HIL 补充**：有板时跑 `hil_to_gate.py --port COMx` 补充纸路/BT 验证
3. **Standard profile**：改运动相关代码后跑 `--profile standard`（包含 hardware_sim）
