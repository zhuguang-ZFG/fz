# <短标题>

```yaml
risk: low   # low | med | high  （A2A_SPEC_STRICT 必填）
repo: fz    # fz | Grbl_Esp32 | QWEN3.0
gate_touch: G1   # G0|G1|G2|G3|G4|G5|none
taxonomy: [D2]
```

owns: <逗号分隔的相对路径，禁止越权改其它文件>

## paths（仅允许改这些；与 owns 一致）

- `path/a`
- `path/b`

## goal

一句话。

## gates（机械验收 — A2A_SPEC_STRICT 识别 ```gates）

```gates
# 必须可机跑；Kimi 亲自重跑，不采信 RESULT 口述
# Agent vibe 默认：PC 主机 SIL（先于烧录）
cd D:/Users/zhugu/fz
python scripts/agent_gate.py --profile standard
# expect: exit 0
# report: results/agent_gate_last.json
# 若只动协议：python scripts/agent_gate.py --profile quick
# 发版前：python scripts/full_release_smoke.py
# 可选：pytest -q
```

## 验收（人类可读；与 gates 命令对齐）

```text
cd D:/Users/zhugu/fz
python scripts/agent_gate.py --profile standard
# expect: 0
# on fail: read results/agent_gate_last.json agent_hints
```

## 禁止

- 无负例 / 跳过失败 / 改 scope 隐瞒  
- 声称「本 fork 固件已验证」若只跑了 grblHAL_sim  
- 未写 RESULT.md  
- 无 ```gates 块就派工（A2A_SPEC_STRICT=1 时 send 会被拒）

## out_of_scope

- 芯片 QEMU 全栈产品门禁  
- 未授权路径  

## 完成后

在同目录写 `RESULT_<slug>.md`：真实命令、exit code、日志路径、遗留问题。  
A2A 消息只发短指针：`risk: … 读取 D:/Users/zhugu/fz/a2a_workorders/<file>.md 并照单执行。`
