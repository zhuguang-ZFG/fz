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
| R10 | Multi-source sim research (GH/官方/中文/论坛) | **done** | `docs/specs/2026-07-14-multi-source-sim-research.md` |
| R11 | Host SIL deep-opt (shared TCP, ports, cases) | **done** | `sim_common/` + protocol/hw refactor |
| R12 | Agent vibe gate (proactive PC test) | **done** | `scripts/agent_gate.py` + `docs/AGENT_VIBE_CODING.md` |
| R13 | JSON hw cases + per-move StepOracle + stdin inject | **done** | `case_runner.py` + `cases/` |
| R14 | Community PC sim case pack + block oracle | **done** | protocol e33/CAM words; block_oracle |
| R15 | Soft src/tests + $G/$I status pack | **done** | `cases/soft` + `cases/status` |
| R16 | sim_rerun + soft_divergence + --only | **done** | `scripts/sim_rerun.py` |
| R17 | EDA-style honesty + agent_loop | **done** | `release_honesty.py` / `agent_loop.py` |
| R18 | Wokwi scaffold (Espressif third-party) | **done** | `chip_sim/wokwi/` + `run_wokwi_smoke.py` |
| R19 | Golden replay + fault-inject must-red | **done** | `cases/golden` + `--integrity-inject` |
| R20 | 社区 ESP 模拟文 vs 官方纠偏 | **done** | `docs/specs/2026-07-14-community-esp-sim-vs-official.md` |
| R21 | Shared protocol sim session | **done** | `sim_common/sim_session.py` + agent_gate reuse |
| R22 | GitHub Actions host SIL | **done** | `.github/workflows/host_sil.yml` |
| R23 | Golden recorder from last_report | **done** | `scripts/golden_record.py` |
| R24 | Soft allowlist machine check | **done** | `soft/allowlist.yaml` + `soft_allowlist.py` |
| R25 | MUST proactive agent_gate (三仓 AGENTS) | **done** | Grbl/QWEN/fz `AGENTS.md` hard rules |
| R26 | CI standard job (schedule + dispatch profile=standard) | **done** | `.github/workflows/host_sil.yml` |
| R27 | Report age tightening (default 24h; release override 168h) | **done** | `scripts/release_honesty.py` default 24h |
| R28 | CI hygiene: schedule skips quick (Claude residual) | **done** | `host_sil.yml` if event != schedule |
| R33 | protocol JSON case structural check | **done** | `protocol_sim/validate_cases.py` in gate+CI |
| R32 | Linux host SIL CI (build sim + gate) | **parked** | scripts/job kept; **not** on push/PR (low ROI) |
| R34 | sim log triage one-page | **done** | `scripts/sim_log_triage.py` → `results/triage_last.md` |
| R35 | gate red auto fail-slice print | **done** | `agent_gate` `_finish` on overall≠0 |
| R36 | HIL serial log archive + index | **done** | `hil/archive_serial_log.py` + hil_to_gate --port |
| R37 | PC-only fail pack expand (no HIL) | **done** | +6 hard fail + soft CAM + goldens |
| R38 | Agent observe surface (always-on) | **done** | `agent_observe.py` + gate integration |
| — | Real product paper/BT HIL | **human** | Grbl `ACCEPTANCE_CHECKLIST` + filled g3 YAML |
| — | ESP32 chip QEMU **product** hard gate | **out of scope** | experimental smoke only |

## Commands

```powershell
cd D:\Users\zhugu\fz
# Agent 主动门禁（vibe coding，默认 standard/auto）
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python scripts/agent_gate.py
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
- 社区文 `idf.py simulate` **不可信**；官方是 `idf.py qemu` + host-apps — 见 [community-esp-sim-vs-official](./specs/2026-07-14-community-esp-sim-vs-official.md)。

## Residual gaps → solutions

See **[RESIDUAL_GAPS_SOLUTIONS.md](./RESIDUAL_GAPS_SOLUTIONS.md)** (community options for G3b HIL, real OTA, QEMU scope, A2A registry slash bug).