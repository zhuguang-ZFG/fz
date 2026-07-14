# HIL helpers (real ESP32 — optional)

Community: [Golioth HIL](https://blog.golioth.io/golioth-hil-testing-part1/) (self-hosted board), serial log evidence, USB flash before full Wi-Fi OTA.

## G3a — general serial smoke

```powershell
pip install pyserial
python hil/serial_smoke.py --port COM7 --out results/g3a.json
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

## Offline tests

```powershell
python -m unittest discover -s hil -p "test_*.py" -v
```
