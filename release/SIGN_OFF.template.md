# 发布签字 — <version>

机检（类 KiCad 出板前 DRC 汇总，可脚本）：

```powershell
python scripts/agent_gate.py --profile deep
python scripts/release_honesty.py --require-agent-gate --scope release/scopes/<scope>.yaml `
  --g3-evidence <filled> --g4-evidence <filled>
# 报告: results/release_honesty_last.json  verdict 应为 ready_to_sign
```

- [ ] `results/agent_gate_last.json` overall_status=**pass**（附路径/时间）
- [ ] `results/release_honesty_last.json` verdict=**ready_to_sign**（非 pending/blocked）
- [ ] `SUMMARY.md` 无未解释的 **fail**
- [ ] `blockers_open` 为空，或已 **executive_waive** 并记录在 scope
- [ ] **G3b** 纸路/BT/SEG 清单已完成（建议两轮），证据在 bundle（若 scope 开启）
- [ ] 理解：`grblHAL_sim` / `agent_gate` 绿 **不能** 代替本产品固件二进制与纸路/BT
- [ ] soft_divergence 高分歧已审阅（`protocol_sim/results/soft_divergence.json`）
- [ ] 未测项已列为 Unknown→按 Blocker 处理或已 waive
- [ ] **未**在发布说明中使用禁止话术（纸路已验证/全真仿真/与 grblHAL 完全一致…）

**残余风险（必填）：**



**签字人：** ____________  **日期：** ____________
