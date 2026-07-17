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
- `results/runs/<run-id>/report.json` / `manifest.json`
- `results/runs/<run-id>/step.log` / `block.log` / `EEPROM.DAT`

The `*_last` files are atomic compatibility copies for existing gate and triage
scripts. Every invocation uses a fresh run directory, so prior motion and EEPROM
state cannot overwrite the evidence for a later run.

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
python hardware_sim/run_hw_sim.py --start-sim --only move_x_10
python hardware_sim/run_hw_sim.py --start-sim --repeat 20
```

`--repeat N` starts a separate simulator process with fresh logs and EEPROM for
each iteration, then writes an aggregate `last_hw_report.json`. Step windows wait
for cumulative counters to settle and compare the latest signed counters; the
session-wide lower bound still uses maximum absolute travel.

Inject protocol: `docs/sim_inject_protocol.md`  
Plant: `plant.py` (TCP `!`/`~`; stdin PIPE best-effort / soft on Windows).  
JSON schema: `case_runner.py` docstring; files in `cases/`.

## Deterministic paper Plant 2.0

`paper_plant.py` models paper position, feed speed, sensor debounce, overtravel,
and fail-closed controller behavior on a deterministic virtual clock. The fault
campaign covers nominal feed, slip, jam, missing paper, stuck sensors, sensor
bounce, motor reverse, timeout, and pairwise slip+bounce/slip+jam combinations without wall-clock sleeps:

```powershell
python hardware_sim/run_paper_plant_campaign.py
python hardware_sim/run_paper_plant_campaign.py --only jam --only sensor_bounce
python hardware_sim/run_paper_plant_interactions.py
python hardware_sim/run_paper_transient_campaign.py
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'; python hardware_sim/run_paper_firmware_contract.py
```

The report is written to `hardware_sim/results/paper_plant_campaign.json` and is
available through the Agent API `run_paper_plant` operation and `paper_plant`
report resource. Full campaigns enforce fault-coverage closure. This is a
mechanical/sensor model, not proof of ESP32 scheduling, real torque/friction,
Bluetooth transport, or physical paper-path HIL.

The interaction runner exhaustively evaluates a bounded 48-case space across
paper presence, feed speed, drive faults, and sensor faults. Each configuration
is replayed twice for determinism and checked for fail-closed completion,
terminal motor shutdown, a final transition, and known terminal reasons. Its
report proves 44/44 pairwise value interactions and emits `minimal_failure`
when any property fails. This follows the combination-coverage pattern used by
Microsoft PICT while retaining exhaustive coverage because virtual time makes
the complete bounded product inexpensive. Agents can invoke the same fixed
runner through `run_paper_interactions` and read `paper_interactions` evidence.

`paper_firmware_contract.json` is the reviewed dictionary between product
firmware constants and Plant abstractions. The contract runner extracts numeric
macros directly from `GRBL_ROOT`, checks the selected machine limits and sensor
policy, and verifies declared Plant scaling. For example, the virtual Plant's
2500 ms timeout is explicitly recorded as a 1:6 acceleration of the firmware's
15000 ms timeout; it is no longer an unexplained duplicate constant. Any change
on either side fails `paper_contract` until the dictionary and rationale are
reviewed. Agents can invoke `run_paper_contract` or read `paper_contract`.

`run_paper_transient_campaign.py` schedules recoverable jam, sensor override,
and speed-scale windows on the virtual clock. Windows use `[start_ms, end_ms)`
semantics and are applied before each tick. The campaign checks deterministic
replay, recovery versus fail-closed outcomes, terminal motor shutdown, and
shrinks failing windows to a tick-granularity local minimum. Agents can invoke
`run_paper_transients` or read `paper_transients` evidence.
## Open-source fusion

See `fusion_notes.md` and repo-wide [opensource-sim-fusion-catalog](../docs/specs/2026-07-14-opensource-sim-fusion-catalog.md).  
Chip-level tools (QEMU/Wokwi/Renode) live under `chip_sim/` — not required for this runner.
