# HIL→gate one-click + A2A strict template

```yaml
risk: med
repo: fz
gate_touch: G3,G4,G5
taxonomy: [D9,D10]
```

owns: a2a_workorders/TEMPLATE.md, scripts/hil_to_gate.py, scripts/test_hil_to_gate.py, hil/README.md, docs/STATUS.md, README.md

## paths（仅允许改这些）

- `D:/Users/zhugu/fz/a2a_workorders/TEMPLATE.md`
- `D:/Users/zhugu/fz/scripts/hil_to_gate.py`
- `D:/Users/zhugu/fz/scripts/test_hil_to_gate.py`
- `D:/Users/zhugu/fz/hil/README.md`
- `D:/Users/zhugu/fz/docs/STATUS.md`
- `D:/Users/zhugu/fz/README.md`

## goal

1. A2A 工单模板通过 `A2A_SPEC_STRICT=1`（`risk` + ```` ```gates ````）。
2. `scripts/hil_to_gate.py`：无板离线 unittest+smoke；有板 paper_m30 / dual_flash → merge → release_gate。

## gates

```gates
cd D:/Users/zhugu/fz
python -m unittest discover -s hil -p "test_*.py" -v
python -m unittest scripts.test_hil_to_gate -v
python scripts/hil_to_gate.py --skip-smoke
python scripts/full_release_smoke.py
# expect: 0
```

## 验收

```text
python scripts/hil_to_gate.py --skip-smoke
# expect: 0 + OFFLINE message
# with board (operator):
# python scripts/hil_to_gate.py --port COM7 --no-expect-paper-log
# $env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python scripts/hil_to_gate.py --port COM7 --with-g4
```

## 禁止

- 默认要求真机
- 声称 Wi-Fi OTA 已自动验证（USB dual flash ≠ OTA）
- QEMU 产品门禁

## out_of_scope

- mcp-a2a-bridge daemon 代码（仅消费 strict 规则）
- 产品 paper_system 固件修改

## 完成后

`a2a_workorders/RESULT_hil_to_gate_pipeline.md`
