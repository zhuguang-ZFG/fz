# RESULT R38 — Agent observe surface

## Delivered

- `scripts/agent_observe.py` → `results/agent_observe_last.{md,json}`
- findings: hard | soft | info | optimize + next_actions + block_done_claim
- Wired into `agent_gate` after triage (always, green or red)
- `print_observe_brief` on every gate finish
- tests: `scripts/test_agent_observe.py`
- docs: STATUS, AGENT_VIBE, fz AGENTS.md

## Agent loop

```
agent_gate → agent_observe_last.md → (fix) → sim_rerun → agent_gate
```
