# R42 product soft divergence docs (strategy A/C)

```yaml
risk: low
repo: fz
gate_touch: none
taxonomy: [D2, honesty]
```

owns: `protocol_sim/cases/soft/`, `docs/PRODUCT_SOFT_DIVERGENCE.md`, `docs/STATUS.md`, `docs/AGENT_VIBE_CODING.md`, `scripts/agent_observe.py` (soft action text only if needed), `a2a_workorders/RESULT_r42_product_soft_divergence.md`

Optional product pointer (if easy): `D:/Users/Grbl_Esp32/Grbl_Esp32/src/tests/` README or comment in parsetest.nc / user_io.nc — only comments/docs, no parser rewrite.

## goal

After real combat with GRBL_ROOT product samples:
- **parsetest**: product dialect (inline comments / glued axes) may error:25 on grblHAL_sim — strategy **A/C**: document as expected soft divergence; do **not** force product parser to match sim unless product also rejects.
- **user_io**: M62/M63/M67 are product I/O — **HIL/product only**; host SIL full red is expected radar, not a bug to "fix" by gutting features.

## gates

```gates
cd D:/Users/zhugu/fz
python protocol_sim/validate_cases.py
python scripts/soft_allowlist.py
python scripts/agent_observe.py --quiet
python scripts/agent_gate.py --profile quick
# expect: exit 0; soft still may warn high_divergence but allowlist pass
```

## 禁止

- Rewrite GCode.cpp to silence soft
- Remove M62 support
- Claim paper/BT verified
