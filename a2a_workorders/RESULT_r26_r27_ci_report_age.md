# R26 CI standard + R27 report age — Result

**Date:** 2026-07-14
**Risk:** med
**Gate touch:** G1
**Taxonomy:** D2, honesty

## Changes

| ID | File | Change |
|----|------|--------|
| R26 | `.github/workflows/host_sil.yml` | Added schedule (weekly Mon 06:00), `workflow_dispatch` input `run_standard`, new `agent-gate-standard` job running `agent_gate --profile standard`, uploading `agent-gate-standard` artifact |
| R27 | `scripts/release_honesty.py` | Changed `--max-age-hours` default from 168 to 24; updated help text |
| R27 | `scripts/agent_loop.py` | `--honesty` now passes `--max-age-hours 24` to release_honesty |
| R27 | `scripts/test_release_honesty.py` | Added `test_stale_report_blocker` unit test; increased existing test max-age to 7200 |
| DOC | `docs/STATUS.md` | Added R26 and R27 rows |
| DOC | `docs/AGENT_VIBE_CODING.md` | CI section updated for R26/R27 |

## Gates

- [x] `python -m py_compile scripts/release_honesty.py`
- [x] `python -m unittest scripts.test_release_honesty -v`
- [x] `python scripts/agent_gate.py --profile quick`
- [x] `python scripts/release_honesty.py --require-agent-gate --allow-pending-hil --max-age-hours 24`

## A2A fleet

| Role | Result |
|------|--------|
| Reasonix implement | completed (sandbox→D: fz writes) |
| Kimi L1 re-gate | unittest 3/3, agent_gate quick 0, honesty 24h 0 |
| Atom | VERDICT pass, BLOCKERS none |
| Claude xreview | APPROVE; residual: schedule also runs quick; mtime cache caveat |

## Verdict

R26/R27 implemented per workorder. No QEMU/product hard gate changes. No protocol cases logic changes.
standard job timeout set to 40m by Kimi after review.
