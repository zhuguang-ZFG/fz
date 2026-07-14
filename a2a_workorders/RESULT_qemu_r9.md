# RESULT: QEMU experimental path R9

**date:** 2026-07-14

## Commands

```text
python -m unittest discover -s chip_sim -v
# exit 0

GRBL_ROOT=D:/Users/Grbl_Esp32 python chip_sim/build_flash_image.py
# 4MB flash_image_4mb.bin exit 0

# downloaded espressif qemu 9.2.2 win mingw32 → vendor/espressif_qemu/

ESP_QEMU=.../extract/qemu/bin/qemu-system-xtensa.exe python chip_sim/run_qemu_smoke.py
# rom_boot_ok=true app_banner_ok=false app_panic_seen=true exit 0
```

## Interpretation

Chip SIL path **works** through ROM + 2nd-stage bootloader. Product Arduino app **panics** under QEMU. Host SIL (grblHAL) remains the hard daily gate.
