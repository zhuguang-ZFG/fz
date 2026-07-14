# 与产品仓集成

## 指针（在 Grbl_Esp32 / QWEN 中引用）

仿真实现与设计的 **唯一主仓** 为：

https://github.com/zhuguang-ZFG/fz

本地默认路径建议：`D:/Users/zhugu/fz`（可用 `FZ_ROOT` 覆盖）。

**上线前：** 按 [pre-release defect gate](specs/2026-07-14-pre-release-firmware-defect-gate-design.md) 跑完整 G0–G5；产品纸路实机表仍以 Grbl 仓 `docs/ACCEPTANCE_CHECKLIST.md` 为准并归档进 `fz/release/bundles/`。

## Grbl_Esp32

- 删除或停用仓内 `tools/sim_regression`、`tools/grblhal_sim` 的继续开发；改为文档指向本仓。  
- 日常协议门禁：

```powershell
$env:FZ_ROOT = 'D:\Users\zhugu\fz'
python $env:FZ_ROOT\protocol_sim\run_regression.py --start-sim
```

- 可选：`$env:GRBL_ROOT = 'D:\Users\Grbl_Esp32'` 以启用 `--include-repo-tests`（若配置）。

## QWEN3.0

- FakeDevice / motion 契约仍可在 QWEN 仓测试树。  
- 跨仓 fullchain runner 读取 `FZ_ROOT` 启动 L1，再跑 L2。

## 推送本仓

```powershell
cd D:\Users\zhugu\fz
git add -A
git status
git commit -m "Initial fz simulation bench: specs, protocol_sim, vendored grblHAL_sim"
git push -u origin main
```
