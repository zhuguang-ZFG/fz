# RESULT R32 — Linux host SIL CI

## Delivered

- `scripts/build_grblhal_sim.sh` — cmake build of grblHAL/Simulator → `vendor/grblhal_sim/bin/grblHAL_sim`
- `sim_common/find_sim.py` — Linux ELF + `bin/linux/` + PATH
- `.github/workflows/host_sil.yml` — job `agent-gate-quick-linux` on `ubuntu-latest`
- `docs/ops_linux_sim_ci.md` — GH default + optional VPS self-hosted (no secrets)

## Not done here

- No VPS login, no password storage
- Self-hosted runner registration is operator-side

## Product decision (follow-up)

**Parked:** Linux job no longer on push/PR (low ROI). Opt-in via `run_linux_quick` dispatch only.  
Daily path remains Windows `agent_gate` + vendored `.exe`.

## Gates

Local Windows: existing agent_gate still uses .exe  
Linux: manual dispatch only
