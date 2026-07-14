# Combat: QWEN3.0 + fz (2026-07-14)

## Ran

| Check | Result |
|-------|--------|
| QWEN pytest motion trio | **60 passed** (`test_device_gateway_motion_contract`, `test_device_motion`, `test_motion`) |
| fz `run_g2_qwen_contracts.py` | **pass** exit 0 (~5.6s, 47 tests in G2 default set) |
| fz `agent_gate --profile quick` | **pass** exit 0; soft WARN parsetest*/user_io (Grbl product, R42) |
| `full_release_smoke --with-cloud` | **timeout 180s** this session — incomplete; G2 alone already green |

## What this means for QWEN

- **Cloud motion contracts / FakeDevice path: healthy** under project venv310.
- **AGENTS hard rule 7** still applies when editing G-code/gateway motion — must also run fz gate, not only pytest.
- Soft high divergence is **Grbl_Esp32 sample vs grblHAL_sim** (documented R42), not a QWEN API regression.
- Host SIL does **not** validate QWEN HTTP/voice/miniprogram; those stay pytest/ruff/deploy.

## Agent read

- QWEN: pytest output
- fz: `results/agent_observe_last.md`, G2 JSON if written by runner
