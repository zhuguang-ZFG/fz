# Soft stream allowlist (product samples vs grblHAL)

Soft cases (`cases/soft/*.nc` and `--include-repo-tests`) **never hard-fail** the protocol suite.
They record ok/error divergence for agents (`results/soft_divergence.json`).

**Policy (R42 strategy A/C):** see **`docs/PRODUCT_SOFT_DIVERGENCE.md`**.

**Machine check (R24):** `protocol_sim/cases/soft/allowlist.yaml`

```powershell
python scripts/soft_allowlist.py
# report: protocol_sim/results/soft_allowlist_last.json
# agent_gate: warn on quick/standard; hard-fail on deep/firmware if unknown high
```

## Expected high-divergence product samples

| Sample | Why host SIL diverges | Action (R42) |
|--------|----------------------|--------------|
| `user_io.nc` | Product `M62`/`M63`/`M67` | **HIL/product only** — do not remove features for sim |
| `parsetest.nc` / `parsetest_comments` | Inline comments / glued axes → often `error:25` on sim | **Dialect radar** — document; optional fix tests if product also rejects |
| `spindle_testing.nc` | Spindle + comments | Soft; low priority |

## Rules

1. **Do not** convert product custom G/M to hard `cases/pass` without grblHAL-compatible golden.
2. Soft high_divergence is a **signal**, not a ship block on quick — honesty may WARN.
3. Golden hard cases stay grblHAL-compatible only.
4. **Do not** rewrite product parser solely to silence soft (unless product HIL also fails and goal is strict Grbl compat).
