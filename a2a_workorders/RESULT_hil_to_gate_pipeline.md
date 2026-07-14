# RESULT: HIL→gate + A2A strict template

**date:** 2026-07-14  
**risk:** med  
**agent:** Kimi (local implement)

## Commands run

```text
cd D:/Users/zhugu/fz
python -m unittest discover -s hil -p "test_*.py" -v
# exit 0 (3 tests)

python -m unittest discover -s scripts -p "test_*.py" -v
# exit 0 (9 tests incl. test_hil_to_gate)

python scripts/hil_to_gate.py --skip-smoke
# exit 0; OFFLINE message printed

python scripts/full_release_smoke.py
# exit 0; bundle pre-release-min-20260714-211637 G1+G5
```

## Deliverables

- `a2a_workorders/TEMPLATE.md` — `risk`, `owns:`, ```` ```gates ```` for A2A_SPEC_STRICT
- `scripts/hil_to_gate.py` — offline + `--port` G3b merge + optional `--with-g4`
- `scripts/test_hil_to_gate.py`
- docs: `hil/README.md`, `STATUS.md` R6, `README.md`, residual gaps P0b

## Board path (not run this session)

```text
python scripts/hil_to_gate.py --port COMx
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python scripts/hil_to_gate.py --port COMx --with-g4
```

## Residual

- Operator must fill remaining g3/g4 YAML (keys, true Wi-Fi OTA)
- A2A MCP process must load bridge with normalize_agent_url; strict env optional
