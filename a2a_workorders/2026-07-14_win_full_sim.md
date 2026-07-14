# Windows full host SIL entry (R7)

```yaml
risk: med
repo: fz
gate_touch: G1
taxonomy: [D2,D9]
```

owns: scripts/win_full_sim.py, scripts/win_full_sim.ps1, scripts/test_win_full_sim.py, protocol_sim/cases/, docs/STATUS.md, README.md

## paths

- `scripts/win_full_sim.py`
- `scripts/win_full_sim.ps1`
- `scripts/test_win_full_sim.py`
- `protocol_sim/cases/**`
- `docs/STATUS.md`, `README.md`, `protocol_sim/README.md`, `docs/RESIDUAL_GAPS_SOLUTIONS.md`

## goal

One-command Windows host SIL stacking grblHAL_sim protocol + hardware plant + offline units + honesty gaps report. Expand protocol fail cases per community grblHAL error surface.

## gates

```gates
cd D:/Users/zhugu/fz
python -m unittest scripts.test_win_full_sim -v
python scripts/win_full_sim.py
# expect: 0
```

## 禁止

- Claiming product paper/BT/OTA/QEMU from win_full_sim green
- Requiring USB board for default path

## 完成后

`RESULT_win_full_sim.md`
