# fz — Agent rules (host SIL)

This repo is the **only** home for Grbl/写字机 **PC simulation gates**.  
Product firmware: `D:/Users/Grbl_Esp32` (or `GRBL_ROOT`). Cloud: `D:/QWEN3.0` (optional `QWEN_ROOT`).

**hutuji 商业基线：** Grbl 分支 `fix/panel-hold-after-align-116687e`；枢纽约束见 `D:/Users/hutuji/docs/agent-constraint-matrix.md` 与 `docs/agent-anti-drift.md`。  
**契约对齐方向：** `hardware_sim/paper_firmware_contract.json` 必须跟随商业固件常量；**禁止**为门禁绿去改换纸机械/时序。  
`wokwi_startup` 为可选云启动：失败保留证据，但**不**单独阻断 host SIL overall（见 `scripts/agent_gate.py`）。

**What you are equipped with:** not a full-chip twin — a **PC exam + medical record + anti-BS rails**.  
One-pager: [`docs/AGENT_SURFACE.md`](docs/AGENT_SURFACE.md).

## HARD RULE — always run agent_gate proactively

When you edit **anything** under this tree that affects:

- `protocol_sim/` / `hardware_sim/` / `sim_common/` / `scripts/agent_gate.py` / cases  
- or you are finishing work that product agents will trust as “PC verified”

you **MUST** run:

```powershell
cd D:\Users\zhugu\fz
$env:GRBL_ROOT = 'D:\Users\Grbl_Esp32'   # if available
python scripts/agent_gate.py --profile standard
# quick is OK for pure protocol case edits; standard default for harness changes
```

**Before** claiming done / fixed / ready for product agents:

1. Exit code **0** and `results/agent_gate_last.json` → `overall_status: pass`  
2. Read `results/agent_observe_last.md` (R38) — even when green: soft/optimize findings  
3. On failure: follow `next_actions` + `python scripts/sim_rerun.py --from-last` — do **not** skip  
4. If `agent_should_block_done_claim` is true in observe JSON → **do not** claim fixed  

Observable loop: **gate → observe → fix → sim_rerun → gate**.

Do **not**:

- Claim paper/BT/OTA/product flash from host SIL green  
- Add new sim engines under `Grbl_Esp32`  
- Treat community `idf.py simulate` as the product path (see `docs/specs/2026-07-14-community-esp-sim-vs-official.md`)

## Entry points

| Command | Role |
|---------|------|
| `python scripts/agent_gate.py` | **Primary** agent gate |
| `python scripts/agent_loop.py` | gate → rerun fails → gate |
| `python scripts/release_honesty.py --require-agent-gate --allow-pending-hil` | ship honesty |
| `python scripts/golden_record.py ...` | R23 record goldens |
| `python scripts/soft_allowlist.py` | R24 soft divergence allowlist |

Playbook: `docs/AGENT_VIBE_CODING.md` · Status: `docs/STATUS.md`

## CI

`.github/workflows/host_sil.yml` runs `agent_gate --profile quick` on push/PR (Windows + vendored sim).
