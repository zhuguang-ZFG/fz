# RESULT R19 — Golden replay + fault-inject integrity

**Status:** implemented (local verification required before treat as green)

## Delivered

1. **Golden pack** `protocol_sim/cases/golden/*.json` (8 contracts): G0 smoke, undefined feed, bad number, G999, `$I`/`$G`/`?`, `$C`.
2. **Runner:** `--golden`, `--skip-golden`, default full suite includes golden; writes `protocol_sim/results/golden_last.json`.
3. **Inject packs** `protocol_sim/cases/inject/*.json` (3 false-green scripts).
4. **`--integrity-inject`:** exit 0 only if every inject case fails as a normal case (no false green); writes `integrity_inject_last.json`.
5. **`scripts/test_gate_integrity.py`** unittest.
6. **`agent_gate`:** new hard layer `integrity` before `protocol` on all profiles.
7. Soft allowlist notes: `protocol_sim/cases/soft/ALLOWLIST.md`.

## Agent usage

```powershell
cd D:\Users\zhugu\fz
python scripts/agent_gate.py --profile quick
python protocol_sim/run_regression.py --start-sim --golden
python protocol_sim/run_regression.py --start-sim --integrity-inject
```

## Honesty

Host SIL golden ≠ product paper/BT/OTA. Integrity only proves the **harness** catches wrong expects, not silicon.
