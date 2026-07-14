# RESULT R20 — Community ESP sim article vs official

**Status:** docs only — done

## Delivered

- `docs/specs/2026-07-14-community-esp-sim-vs-official.md`
- Links from STATUS, RESIDUAL_GAPS, fusion catalog, README, AGENT_VIBE_CODING

## Agent takeaway

- Reject `idf.py simulate` / `TARGET=simulate` as product gate.
- Official free chip path: `idf.py qemu` + host-apps + optional Wokwi.
- Product PC path remains `scripts/agent_gate.py` (grblHAL host SIL).
