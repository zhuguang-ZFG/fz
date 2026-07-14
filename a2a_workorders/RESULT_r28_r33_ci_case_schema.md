# RESULT R28 + R33 (community CI hygiene)

## R28
- Weekly schedule: only `agent-gate-standard` (quick skipped via `if: event_name != schedule`)
- Addresses Claude residual: don't pay for quick+standard every Monday

## R33
- `protocol_sim/validate_cases.py` — offline structure for fail/golden/status/inject JSON
- Wired into `agent_gate` (layer `case_schema`) and CI quick job before sim
- Unit: `protocol_sim/test_validate_cases.py`

## Community note
Catch hand-edited protocol fixtures before TCP sim (same idea as offline config/script validation in printer/firmware CI suites).
