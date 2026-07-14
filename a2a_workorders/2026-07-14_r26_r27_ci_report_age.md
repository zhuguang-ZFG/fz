# R26 CI standard + R27 report age

```yaml
risk: med
repo: fz
gate_touch: G1
taxonomy: [D2, honesty]
```

owns: `.github/workflows/host_sil.yml`, `scripts/release_honesty.py`, `scripts/test_release_honesty.py`, `scripts/agent_loop.py`, `docs/STATUS.md`, `docs/AGENT_VIBE_CODING.md`, `a2a_workorders/RESULT_r26_r27_ci_report_age.md`

## paths

- `.github/workflows/host_sil.yml`
- `scripts/release_honesty.py`
- `scripts/test_release_honesty.py`
- `scripts/agent_loop.py` (if honesty flags)
- `docs/STATUS.md`
- `docs/AGENT_VIBE_CODING.md`

## goal

R26: optional GitHub Actions job for `agent_gate --profile standard` (dispatch/schedule; push/PR stay quick).  
R27: tighten agent_gate report max-age when `--require-agent-gate` (default 24h vibe; override with `--max-age-hours`).

## gates

```gates
cd D:/Users/zhugu/fz
python -m py_compile scripts/release_honesty.py
python -m unittest scripts.test_release_honesty -v
python scripts/agent_gate.py --profile quick
python scripts/release_honesty.py --require-agent-gate --allow-pending-hil --max-age-hours 24
# expect: exit 0 after fresh gate
# stale test: unit tests cover age blocker
```

## 禁止

- 产品 QEMU hard gate
- 改 protocol cases 逻辑
- 声称 HIL 已验证

## out_of_scope

- R29 常驻板 HIL
- Linux sim binary

## 完成后

`RESULT_r26_r27_ci_report_age.md` + Kimi re-gate + Atom + Claude xreview
