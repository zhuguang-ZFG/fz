# RESULT_g4_ota_gate

Implemented by Kimi (A2A agents were intermittently unregistered; workorder executed locally per fleet final-owner rule).

## Files

- scripts/g4_ota.py
- scripts/test_g4_ota.py
- release/g4_ota.template.yaml
- release/g4_ota.dev-sample-pass.yaml
- release/scopes/dev-ota.yaml
- scripts/release_gate.py (--g4-evidence, run_g4_ota)

## Commands

```text
python -m unittest discover -s scripts -p "test_*.py" -v  → OK (6 tests)
python scripts/release_gate.py --scope release/scopes/dev-quick.yaml --skip-g0 --only G4 → exit 0 (skipped_no_ota)
python scripts/release_gate.py --scope release/scopes/dev-ota.yaml --skip-g0 --only G4 → exit 3 (unknown)
python scripts/release_gate.py --scope release/scopes/dev-ota.yaml --skip-g0 --only G4,G5 --g4-evidence release/g4_ota.dev-sample-pass.yaml → exit 0
```
