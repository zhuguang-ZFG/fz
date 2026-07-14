# <短标题>

```yaml
risk: low   # low | med | high
repo: fz    # fz | Grbl_Esp32 | QWEN3.0
gate_touch: G1   # G0|G1|G2|G3|G4|G5|none
taxonomy: [D2]
```

## paths（仅允许改这些）

- 

## goal

一句话。

## acceptance（Kimi 会亲自重跑）

```text
# 命令与期望 exit code
python protocol_sim/run_regression.py --start-sim
# expect: 0
```

## 禁止

- 无负例 / 跳过失败 / 改 scope 隐瞒  
- 声称「本 fork 固件已验证」若只跑了 grblHAL_sim  
- 未写 RESULT.md  

## out_of_scope

- 

## 完成后

在同目录写 `RESULT_<slug>.md`：真实命令、exit code、日志路径、遗留问题。
