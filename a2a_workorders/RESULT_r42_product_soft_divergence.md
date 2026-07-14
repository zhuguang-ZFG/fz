# RESULT R42 — Product soft divergence policy A/C

## Decision

- **A/C**: document dialect + HIL-only IO; do not rewrite GCode or remove M62 for sim green.
- Combat evidence: parsetest e25, user_io e20 on grblHAL_sim with GRBL_ROOT samples.

## Delivered

- `docs/PRODUCT_SOFT_DIVERGENCE.md`
- soft allowlist notes + ALLOWLIST.md
- product test comments: `parsetest.nc`, `user_io.nc`
- observe soft actions point at policy doc
- STATUS / AGENT_VIBE / README links

## Gates

agent_gate quick + soft_allowlist + observe (expect hard green, soft WARN allowed)
