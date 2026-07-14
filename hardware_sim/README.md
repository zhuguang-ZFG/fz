# hardware_sim

Baseline **controller bench** on grblHAL_sim (not product firmware).

## Run

```powershell
cd D:\Users\zhugu\fz
python hardware_sim/run_hw_sim.py --start-sim
```

Writes:

- `results/last_hw_report.json`
- `results/step_last.log` / `block_last.log` (when started with `--start-sim`)
- `results/EEPROM_hw.DAT` (isolated settings)

## Design

See `docs/specs/2026-07-14-hardware-sim-optimization-design.md`.

## Contents

| File | Role |
|------|------|
| `run_hw_sim.py` | builtin + JSON cases; per-move StepOracle; plant |
| `case_runner.py` | JSON-driven cases (`cases/*.json`) |
| `cases/*.json` | motion step windows, feed-hold, stdin limit (soft) |
| `step_oracle.py` | parse `-s` logs → mm travel; per-move delta |
| `test_step_oracle.py` | unit tests (no sim) |
| `product_stubs.md` | honest gaps (paper/BT/soft-limit trip) |
| `../sim_common/` | shared GrblTcp, find_sim, free-port |

```powershell
python -m unittest discover -s hardware_sim -p "test_*.py" -v
# default -t 1; JSON cases + per-move StepOracle included
python hardware_sim/run_hw_sim.py --start-sim
python hardware_sim/run_hw_sim.py --start-sim --fast
python hardware_sim/run_hw_sim.py --start-sim --json-only
python hardware_sim/run_hw_sim.py --start-sim --builtin-only
```

Inject protocol: `docs/sim_inject_protocol.md`  
Plant: `plant.py` (TCP `!`/`~`; stdin PIPE best-effort / soft on Windows).  
JSON schema: `case_runner.py` docstring; files in `cases/`.

## Open-source fusion

See `fusion_notes.md` and repo-wide [opensource-sim-fusion-catalog](../docs/specs/2026-07-14-opensource-sim-fusion-catalog.md).  
Chip-level tools (QEMU/Wokwi/Renode) live under `chip_sim/` — not required for this runner.