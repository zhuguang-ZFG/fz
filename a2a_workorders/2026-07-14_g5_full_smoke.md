# G5 hash polish + full release smoke script

```yaml
risk: med
repo: fz
gate_touch: G5
taxonomy: [D9,D10]
```

## paths（仅允许改这些）

- `D:/Users/zhugu/fz/scripts/release_gate.py` (only G5 meta / hash if needed)
- `D:/Users/zhugu/fz/scripts/full_release_smoke.py` (create)
- `D:/Users/zhugu/fz/scripts/full_release_smoke.ps1` (create optional)
- `D:/Users/zhugu/fz/README.md` (add one section for full smoke)
- `D:/Users/zhugu/fz/release/scopes/pre-release-min.yaml` (create)

## goal

1. After G0 success, if firmware `.bin` exists under GRBL_ROOT `.pio/build/release/`, record sha256 in G5 report (optional, non-fatal if missing).
2. Add one-command smoke that runs implementable gates for pre-release (G0 optional, G1, G2 if cloud, G5).

## requirements

### A. G5 firmware artifact hash

In `run_g5_meta` or after G0:
- Look for common PlatformIO outputs:
  - `{GRBL_ROOT}/.pio/build/release/firmware.bin`
  - or `*.bin` under that folder
- Add to g5_security_meta.json:
  - `firmware_bin_path`
  - `firmware_bin_sha256_16` (first 16 hex) or null
- Do not fail G5 if bin missing

### B. full_release_smoke.py

```text
python scripts/full_release_smoke.py [--with-g0] [--with-cloud] [--g3-evidence PATH]
```

- Sets defaults FZ_ROOT = repo root
- Runs release_gate with `release/scopes/pre-release-min.yaml`:
  - paper_path false, bluetooth false, ota false, cloud_qwen false by default
  - if --with-cloud: use dev-cloud or set cloud true
- Always runs G1+G5; G0 if --with-g0 and GRBL_ROOT; G2 if cloud; G3 if evidence
- Prints bundle path and exit code
- Exit with same code as release_gate

### C. pre-release-min.yaml

Safe default for automated smoke without silicon/paper.

## acceptance

```text
cd D:/Users/zhugu/fz
python scripts/full_release_smoke.py
# expect exit 0 (G1+G5 at least)

# if GRBL_ROOT set:
# $env:GRBL_ROOT='D:\Users\Grbl_Esp32'
# python scripts/full_release_smoke.py --with-g0 --g0-mode test_drive
```

## 禁止

- Requiring real hardware for smoke default
- Claiming product paper verified

## 完成后

`D:/Users/zhugu/fz/a2a_workorders/RESULT_g5_full_smoke.md`
