# RESULT R13: JSON cases + per-move StepOracle + stdin inject

## Delivered

- `hardware_sim/case_runner.py` — JSON schema runner (send/expect/inject/step_window)
- `hardware_sim/cases/*.json` — x10/xy5 step windows, undefined feed, TCP hold, stdin limit soft
- `step_oracle.py` — `per_move_delta`, `window_travel_steps`, `snapshot_max_abs`
- `run_hw_sim.py` — default JSON on; stdin PIPE; `--json-only` / `--builtin-only`

## Verify

```text
python -m unittest discover -s hardware_sim -q
python hardware_sim/run_hw_sim.py --start-sim --fast   # exit 0
python hardware_sim/run_hw_sim.py --start-sim          # exit 0; plant + json hold
```

## Honesty

- Stdin hard-limit on Windows is best-effort (`soft: true`); TCP `!` is the reliable plant path.
