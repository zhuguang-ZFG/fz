# Native product simulation

Compiles product-owned pure C++ logic from `GRBL_ROOT` into a PC executable.
This complements grblHAL behavioral simulation by executing code that is also
used by the Grbl_Esp32 firmware.

```powershell
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python native_sim/run_product_core_tests.py
python native_sim/run_product_core_fuzz.py --iterations 20000
python native_sim/run_product_core_coverage.py --iterations 20000
```

Current coverage:

- Bluetooth link-state reduction and critical-message policy
- Bluetooth TX ring FIFO, wrap, overflow, and reset-generation safety
- Paper pulse-profile timing boundaries
- Paper sensor voting and wrap-safe millisecond deadlines

The runner uses ASan and UBSan and writes `native_sim/results/last_report.json`.

`run_product_core_fuzz.py` builds the same product headers into a deterministic
fuzz-smoke binary. It generates randomized BT event streams, critical-message
inputs, ring-buffer operations, paper timing configs, sensor policies, and
wrap-safe deadlines under ASan/UBSan. Failures are reproducible with the reported
seed and are written to `native_sim/results/last_fuzz_report.json`.

`run_product_core_coverage.py` uses LLVM source-based coverage to report line,
function, and region coverage for `PaperSystemCore.h` and `WebUI/BTStateCore.h`.
The summary is written to `native_sim/results/coverage_summary.json` and surfaced
by `agent_observe.py` as an info/optimize finding.
