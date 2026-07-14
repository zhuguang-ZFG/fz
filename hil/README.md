# HIL helpers (real ESP32 — optional)

Community: [Golioth HIL](https://blog.golioth.io/golioth-hil-testing-part1/) (self-hosted board), serial log evidence, USB flash before full Wi-Fi OTA.

## G3a — general serial smoke

```powershell
pip install pyserial
python hil/serial_smoke.py --port COM7 --out results/g3a.json
# R36: full transcript also under results/hil_logs/*_g3a_serial_smoke_*.log
```

## G3b — paper / M30 serial sequences

Maps product `ACCEPTANCE_CHECKLIST` §1 to log patterns (`PaperM30`, `PAGE_END_IMMINENT`).

```powershell
# product machine with paper custom
python hil/paper_m30_serial.py --port COM7 --out results/g3b_paper.json

# test_drive (no paper logs expected)
python hil/paper_m30_serial.py --port COM7 --no-expect-paper-log --out results/g3b_na.json

# merge into evidence YAML
python hil/merge_evidence_patches.py `
  --template release/g3_evidence.template.yaml `
  --patch-json results/g3b_paper.json `
  --out release/g3_evidence.filled.yaml
```

Keys / SEG still need manual `result: pass` in the YAML.

## G4 — USB dual flash (not Wi-Fi OTA)

```powershell
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python hil/dual_flash_usb.py --port COM7 --mode once --out results/g4_usb.json
# A then B upload:
python hil/dual_flash_usb.py --port COM7 --mode twice --out results/g4_usb.json

python hil/merge_evidence_patches.py `
  --template release/g4_ota.template.yaml `
  --patch-json results/g4_usb.json `
  --out release/g4_ota.filled.yaml
```

Then:

```powershell
python scripts/release_gate.py --scope release/scopes/dev-ota.yaml --skip-g0 `
  --g4-evidence release/g4_ota.filled.yaml --only G4,G5
```

## R36 — serial log archive (有板必做)

Community: HIL CI keeps **serial logs as evidence**, not only pass/fail JSON.

| Output | Meaning |
|--------|---------|
| `results/hil_logs/<utc>_<kind>_<port>.log` | full transcript |
| `results/hil_logs/*.meta.json` | path + bytes |
| `results/hil_log_index.md` | one-page index after `hil_to_gate --port` |

Host SIL failures still use `results/triage_last.md` (R34) — different stack.

## One-click HIL → gate

```powershell
# offline (no board): hil unit tests + optional full_release_smoke
python scripts/hil_to_gate.py
python scripts/hil_to_gate.py --skip-smoke

# board: G3a smoke + G3b paper M30 + log archive → merge g3 → release_gate

python scripts/hil_to_gate.py --port COM7
# test_drive without paper logs:
python scripts/hil_to_gate.py --port COM7 --no-expect-paper-log

# + USB dual flash G4 (needs GRBL_ROOT + pio)
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python scripts/hil_to_gate.py --port COM7 --with-g4 --g4-mode once
```

Evidence lands under `results/` (`g3_evidence.filled.yaml`, optional `g4_ota.filled.yaml`).  
Remaining YAML items (keys / true Wi-Fi OTA) still need operator fill — pipeline only patches scriptable fields.

## Offline tests

```powershell
python -m unittest discover -s hil -p "test_*.py" -v
python -m unittest scripts.test_hil_to_gate -v
```
