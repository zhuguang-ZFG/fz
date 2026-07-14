# Soft stream allowlist (product samples vs grblHAL)

Soft cases (`cases/soft/*.nc` and `--include-repo-tests`) **never hard-fail** the protocol suite.
They record ok/error divergence for agents (`results/soft_divergence.json`).

**Machine check (R24):** `protocol_sim/cases/soft/allowlist.yaml`  
```powershell
python scripts/soft_allowlist.py
# report: protocol_sim/results/soft_allowlist_last.json
# agent_gate: warn on quick/standard; hard-fail on deep/firmware if unknown high
```

## Expected high-divergence product samples

| Sample | Why host SIL diverges | Action |
|--------|----------------------|--------|
| `user_io.nc` | Product `M62`/`M63` digital IO / custom | Document; do not promote to hard pass |
| `parsetest.nc` / `parsetest_comments` | Inline comments / product parser quirks → often `error:25` | Soft only; fix product or accept |
| `spindle_testing.nc` | Spindle words / timing vs sim plant | Soft; motion hard cases elsewhere |

## Rules

1. **Do not** convert product custom G/M to hard `cases/pass` without a golden that matches **grblHAL sim** or an explicit product-sim profile.
2. Soft high_divergence is a **signal**, not a ship block on quick — pair with honesty / HIL for paper/BT.
3. Golden hard cases live in `cases/golden/` — only stable grblHAL-compatible contracts.
4. **R23 record goldens:** `python scripts/golden_record.py --from-last --kinds fail --only undefined_feed`
