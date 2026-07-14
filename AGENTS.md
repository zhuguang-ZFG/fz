# fz — Agent rules (host SIL)

This repo is the **only** home for Grbl/写字机 **PC simulation gates**.  
Product firmware: `D:/Users/Grbl_Esp32` (or `GRBL_ROOT`). Cloud: `D:/QWEN3.0` (optional `QWEN_ROOT`).

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
2. On failure: fix using `agent_hints` + `python scripts/sim_rerun.py --from-last` — do **not** skip  

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
