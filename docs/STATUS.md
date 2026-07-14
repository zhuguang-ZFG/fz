# fz implementation status

Last updated: 2026-07-14

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| R0 | Designs + A2A workflow | **done** | `docs/specs/*` |
| R1 | `release_gate` G0/G1/G5 | **done** | `scripts/release_gate.py` |
| R2 | hardware_sim plant/oracle | **done** | `hardware_sim/run_hw_sim.py` |
| R3 | G3a serial + G3 evidence YAML | **done** | `hil/serial_smoke.py`, `g3_evidence*` |
| R4 | G2 QWEN contracts | **done** | `run_g2_qwen_contracts.py` (+ QWEN tests) |
| R5 | G4 OTA evidence + smoke entry | **done** | `g4_ota*`, `full_release_smoke.py` |
| — | Real product paper/BT HIL | **human** | Grbl `ACCEPTANCE_CHECKLIST` + filled g3 YAML |
| — | ESP32 chip QEMU full stack | **out of scope** | design non-goal |

## Commands

```powershell
cd D:\Users\zhugu\fz
python scripts/full_release_smoke.py
python hardware_sim/run_hw_sim.py --start-sim
$env:QWEN_ROOT='D:\QWEN3.0'; python scripts/full_release_smoke.py --with-cloud
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python scripts/full_release_smoke.py --with-g0
```

## Honesty

- Host sim ≠ product binary.
- G3b paper/BT requires operator evidence; gate fails closed if missing when in scope.
