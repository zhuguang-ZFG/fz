# RESULT R21 + R22

## R21 shared protocol sim

- `sim_common/sim_session.py` — start/stop protocol-mode sim (`-n -t 0`)
- `agent_gate` reuses one process for integrity + protocol layers
- hardware_sim still `--start-sim` (needs step/block logs)
- fallback: `--no-shared-sim` or boot failure → per-layer start

## R22 GitHub Actions

- `.github/workflows/host_sil.yml` — windows-latest, `agent_gate --profile quick`
- requires vendored `vendor/grblhal_sim/bin/grblHAL_sim.exe` in git
