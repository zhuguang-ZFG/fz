# protocol_sim

Protocol-level G-code regression against **grblHAL_sim** (ok / error / ALARM).

Does **not** run Grbl_Esp32 product firmware.

## Run

From repo root `fz/`:

```powershell
python protocol_sim/run_regression.py --start-sim
```

Defaults to `vendor/grblhal_sim/bin/grblHAL_sim.exe` if `GRBLHAL_SIM` unset.

## Cases

- `cases/pass/*.nc` — expect ok  
- `cases/fail/*.json` — expect error codes  

Expanded fail set (community CAM / Grbl error surface): bad number, modal conflict, undefined feed, unsupported G/M, arc missing offset (e35), arc radius (e33), G1 no target.

Pass set: smoke, arcs, rapid box, dwell, N-words/spindle, G20/G21, $C dry-run, coolant words. 

## Design

See `docs/specs/2026-07-14-hardware-sim-optimization-design.md` (protocol is the baseline layer) and software fullchain design for cloud SIL.
