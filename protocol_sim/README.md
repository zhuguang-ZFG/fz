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

## Design

See `docs/specs/2026-07-14-hardware-sim-optimization-design.md` (protocol is the baseline layer) and software fullchain design for cloud SIL.
