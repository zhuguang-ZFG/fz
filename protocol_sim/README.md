# protocol_sim

Protocol-level G-code regression against **grblHAL_sim** (ok / error / ALARM).

Does **not** run Grbl_Esp32 product firmware.

## Run

From repo root `fz/`:

```powershell
python protocol_sim/run_regression.py --start-sim
# soft product samples + hard $G/$I status pack included by default
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python protocol_sim/run_regression.py --start-sim --include-repo-tests
```

Defaults to `vendor/grblhal_sim/bin/grblHAL_sim.exe` if `GRBLHAL_SIM` unset.

## Cases

- `cases/pass/*.nc` — expect ok  
- `cases/fail/*.json` — expect error codes  

| Dir | Role |
|-----|------|
| `cases/pass/*.nc` | hard ok |
| `cases/fail/*.json` | hard error codes |
| `cases/status/*.json` | hard `$I`/`$G`/`?`/`$#` contains_any |
| `cases/golden/*.json` | R19 hard gold contracts (included by default) |
| `cases/inject/*.json` | R19 false-green packs — only via `--integrity-inject` |
| `cases/soft/*.nc` | soft product-like streams (never hard-fail gate) |

```powershell
python protocol_sim/run_regression.py --start-sim --golden
python protocol_sim/run_regression.py --start-sim --integrity-inject
# reports: results/golden_last.json , results/integrity_inject_last.json
# R23 record new goldens from last run:
python scripts/golden_record.py --from-last --kinds fail --only NAME --dry-run
# R24 soft allowlist:
python scripts/soft_allowlist.py
# R33 offline JSON structure (before TCP):
python protocol_sim/validate_cases.py
```

Fail set (community CAM): bad number, modal, undefined feed, unsupported G/M, arc e35/e34, G1 no target.  
Pass: smoke, arcs, rapid box, dwell, N-words, G20/G21, $C dry-run, coolant.  
`--include-repo-tests`: soft-stream `GRBL_ROOT/.../src/tests/{parsetest,spindle_testing,user_io}.nc`. 

## Design

See `docs/specs/2026-07-14-hardware-sim-optimization-design.md` (protocol is the baseline layer) and software fullchain design for cloud SIL.
