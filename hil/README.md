# HIL helpers (optional real ESP32)

## G3a serial smoke

```powershell
pip install pyserial
python hil/serial_smoke.py --port COM7 --out release/bundles/manual/g3a_serial.json
```

Then either:

- attach JSON path as informal evidence, or  
- fill `release/g3_evidence.template.yaml` g3a.* items as `pass` with evidence pointing to that JSON.

**Not covered:** paper M30, BT keys, SEG — use product ACCEPTANCE checklist / G3b YAML.
