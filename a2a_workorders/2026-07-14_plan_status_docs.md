# Update plan completion matrix in docs

```yaml
risk: low
repo: fz
gate_touch: none
taxonomy: [D11]
```

## paths

- `D:/Users/zhugu/fz/docs/specs/2026-07-14-pre-release-firmware-defect-gate-design.md`
- `D:/Users/zhugu/fz/docs/STATUS.md` (create)
- `D:/Users/zhugu/fz/README.md`

## goal

Document what is implemented vs remaining so "full plan" status is honest.

## requirements

Create `docs/STATUS.md` table:

| ID | Item | Status | Evidence command |
|----|------|--------|------------------|
| R0 | designs | done | docs/specs/* |
| R1 | release_gate G0/G1/G5 | done | scripts/release_gate.py |
| R2 | hardware_sim plant/oracle | done | hardware_sim/run_hw_sim.py |
| R3 | G3a serial + G3 evidence YAML | done | hil/serial_smoke.py, g3_evidence* |
| R4 | G2 QWEN contracts | done | run_g2_qwen_contracts.py |
| R5 | G4 OTA evidence | in progress / done after sibling WO | g4_ota* |
| — | Real product paper HIL | human | ACCEPTANCE_CHECKLIST |
| — | Chip QEMU | out of scope | — |

Update pre-release design §7 roadmap statuses briefly.
Update README "当前能力" one-liner.

## acceptance

```text
test -f D:/Users/zhugu/fz/docs/STATUS.md
```

## 完成后

`RESULT_plan_status_docs.md`
