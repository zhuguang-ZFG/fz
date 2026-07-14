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
| `run_hw_sim.py` | motion delta, travel settings, soft-limit gate, step logs |
| `step_oracle.py` | parse `-s` logs → mm travel |
| `test_step_oracle.py` | unit tests (no sim) |
| `product_stubs.md` | honest gaps (paper/BT/soft-limit trip) |

```powershell
python -m unittest hardware_sim/test_step_oracle.py -v
python hardware_sim/run_hw_sim.py --start-sim
```

Next: I/O plant inject (limit/probe), tighter StepOracle per-move windows.
