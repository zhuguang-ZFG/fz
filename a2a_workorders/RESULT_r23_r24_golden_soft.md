# RESULT R23 + R24

## R23 golden_record

- `scripts/golden_record.py`
- `--from-last` / `--from-case` / `--dry-run` / `--force`
- Never records soft; prefers source fail/status JSON for setup

## R24 soft allowlist

- `protocol_sim/cases/soft/allowlist.yaml`
- `scripts/soft_allowlist.py` → `soft_allowlist_last.json`
- `agent_gate`: layer `soft_allowlist` — warn (still pass) on quick/standard; **fail** on deep/firmware if unknown high
