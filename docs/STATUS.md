# fz implementation status

Last updated: 2026-07-14

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| R0 | Designs + A2A workflow | **done** | `docs/specs/*` |
| R1 | `release_gate` G0/G1/G5 | **done** | `scripts/release_gate.py` |
| R2 | hardware_sim plant/oracle | **done** | `hardware_sim/run_hw_sim.py` |
| R3 | G3a serial + G3 evidence YAML | **done** | `hil/serial_smoke.py`, `g3_evidence*` |
| R3+ | G3b paper M30 serial helper | **done** | `hil/paper_m30_serial.py` (+ merge patches) |
| R5+ | USB dual-flash G4 helper | **done** | `hil/dual_flash_usb.py` |
| R4 | G2 QWEN contracts | **done** | `run_g2_qwen_contracts.py` (+ QWEN tests) |
| R5 | G4 OTA evidence + smoke entry | **done** | `g4_ota*`, `full_release_smoke.py` |
| R6 | A2A strict template + HIL→gate | **done** | `a2a_workorders/TEMPLATE.md`, `scripts/hil_to_gate.py` |
| R7 | Windows full host SIL entry | **done** | `scripts/win_full_sim.py` (+ expanded protocol cases) |
| R8 | Open-source sim fusion + chip probe | **done** | fusion catalog + `chip_sim/probe_chip_tools.py` |
| R9 | QEMU flash image + smoke helpers | **done** | `build_flash_image` / `run_qemu_smoke` / install ps1 |
| — | Real product paper/BT HIL | **human** | Grbl `ACCEPTANCE_CHECKLIST` + filled g3 YAML |
| — | ESP32 chip QEMU **product** hard gate | **out of scope** | experimental smoke only |

## Commands

```powershell
cd D:\Users\zhugu\fz
# 全 Win 主机仿真（协议+硬件台架+单测+诚实缺口报告；非芯片/非纸路）
python scripts/win_full_sim.py
# 可选：探测本机 Espressif QEMU / Wokwi / Renode（不装也能绿）
python scripts/win_full_sim.py --with-chip-probe
python chip_sim/probe_chip_tools.py --firmware-hint
# QEMU experimental (need install + PIO build):
# .\chip_sim\install_qemu_windows.ps1
# $env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python chip_sim/build_flash_image.py
# python chip_sim/run_qemu_smoke.py
# .\scripts\win_full_sim.ps1
python scripts/full_release_smoke.py
python scripts/hil_to_gate.py --skip-smoke
# with board: python scripts/hil_to_gate.py --port COM7 [--with-g4]
python hardware_sim/run_hw_sim.py --start-sim
$env:QWEN_ROOT='D:\QWEN3.0'; python scripts/full_release_smoke.py --with-cloud
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python scripts/full_release_smoke.py --with-g0
```

## Honesty

- Host sim ≠ product binary.
- G3b paper/BT requires operator evidence; gate fails closed if missing when in scope.

## Residual gaps → solutions

See **[RESIDUAL_GAPS_SOLUTIONS.md](./RESIDUAL_GAPS_SOLUTIONS.md)** (community options for G3b HIL, real OTA, QEMU scope, A2A registry slash bug).