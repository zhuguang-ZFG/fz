# 与产品仓集成

## 指针（在 Grbl_Esp32 / QWEN 中引用）

仿真实现与设计的 **唯一主仓** 为：

https://github.com/zhuguang-ZFG/fz

本地默认路径建议：`D:/Users/zhugu/fz`（可用 `FZ_ROOT` 覆盖）。

**上线前：** 按 [pre-release defect gate](specs/2026-07-14-pre-release-firmware-defect-gate-design.md) 跑完整 G0–G5。

G3 证据：复制 `release/g3_evidence.template.yaml` → 填写 →  
`python scripts/release_gate.py --scope ... --g3-evidence path/to/filled.yaml`  
产品纸路步骤对齐 Grbl 仓 `docs/ACCEPTANCE_CHECKLIST.md`。

## Grbl_Esp32

- 删除或停用仓内 `tools/sim_regression`、`tools/grblhal_sim` 的继续开发；改为文档指向本仓。  
- **Agent MUST**（`AGENTS.md` HARD RULE）：改 GCode/Protocol/运动相关后主动：

```powershell
$env:FZ_ROOT = 'D:\Users\zhugu\fz'
$env:GRBL_ROOT = 'D:\Users\Grbl_Esp32'
python $env:FZ_ROOT\scripts\agent_gate.py
# 或: D:\Users\Grbl_Esp32\tools\agent_gate.ps1
```

- 仅协议子集：`python $env:FZ_ROOT\protocol_sim\run_regression.py --start-sim`

## QWEN3.0

- FakeDevice / motion 契约仍可在 QWEN 仓测试树。  
- **Agent MUST**（`AGENTS.md` 硬规则 7）：改 U1-Grbl / G 码下发 / 运动协议对齐路径时，**主动**调同一 `agent_gate`（`FZ_ROOT` + 可选 `GRBL_ROOT`）。  
- 纯云/小程序/语音：本仓 pytest 即可，不强制 agent_gate。  
- 跨仓 fullchain runner 读取 `FZ_ROOT` 启动 L1，再跑 L2。

## 推送本仓

```powershell
cd D:\Users\zhugu\fz
git add -A
git status
git commit -m "Initial fz simulation bench: specs, protocol_sim, vendored grblHAL_sim"
git push -u origin main
```
