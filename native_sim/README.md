# Native product simulation

Compiles product-owned pure C++ logic from `GRBL_ROOT` into a PC executable.
This complements grblHAL behavioral simulation by executing code that is also
used by the Grbl_Esp32 firmware.

```powershell
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python native_sim/run_product_core_tests.py
```

Current coverage:

- Bluetooth link-state reduction and critical-message policy
- Bluetooth TX ring FIFO, wrap, overflow, and reset-generation safety
- Paper pulse-profile timing boundaries
- Paper sensor voting and wrap-safe millisecond deadlines

The runner uses ASan and UBSan and writes `native_sim/results/last_report.json`.
