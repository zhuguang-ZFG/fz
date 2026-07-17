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
- Paper sensor-edge search termination used by firmware Steps 2, 6, and 7

The runner uses ASan and UBSan and writes `native_sim/results/last_report.json`.

`run_product_core_fuzz.py` builds the same product headers into a deterministic
fuzz-smoke binary. It generates randomized BT event streams, critical-message
inputs, ring-buffer operations, paper timing configs, sensor policies, and
wrap-safe deadlines under ASan/UBSan. Failures are reproducible with the reported
seed and are written to `native_sim/results/last_fuzz_report.json`.

`run_product_core_coverage.py` uses LLVM source-based coverage to report line,
function, and region coverage for `PaperSystemCore.h` and `WebUI/BTStateCore.h`.
The summary is written to `native_sim/results/coverage_summary.json` and surfaced
by `agent_observe.py` as an info/optimize finding. Repository thresholds live in
`native_sim/coverage_policy.json`; coverage below any configured line, function,
region, or branch minimum fails the native coverage gate. Pass `--policy PATH`
to evaluate an experimental policy without editing the repository baseline.

## Product protocol policy trace

`run_protocol_decision_trace.py` compiles the firmware-owned
`ProtocolDecisionCore.h` and reports the paper-change/license motion policy on
PC. It checks explicit `G0`–`G3`, comments, line numbers, and modal axis-only
motion without classifying setup commands such as `G10` or `G92` as movement.

```powershell
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python native_sim/run_protocol_decision_trace.py --paper-running --modal-motion-active
python native_sim/run_protocol_decision_trace.py --paper-running --stateful-modal G1X1 X2 G80 X3
python native_sim/run_protocol_decision_diff.py --paper-running
```

`--stateful-modal` replays a command sequence and records `modal_before` and
`modal_after` for every line. It models the product policy transition for explicit
`G0`-`G3`, inherited axis-only motion, and `G80` cancellation.

The differential runner pairs each isolated grblHAL response with the product
policy trace. It is evidence for policy/reference compatibility only; it does
not prove full parser equivalence, paper mechanics, or Bluetooth runtime.
Reports are written to `native_sim/results/protocol_decision_trace.json` and
`native_sim/results/protocol_decision_diff.json`.
## Validated protocol scenarios

Repository scenarios live in `native_sim/scenarios/*.json`. The offline validator
rejects malformed lines, non-boolean modes, unknown expectation fields, duplicate
names, and mismatched line/expectation counts before compiling or running code.

```powershell
python native_sim/validate_protocol_scenarios.py
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python native_sim/run_protocol_scenarios.py
python native_sim/run_protocol_scenarios.py --only paper_modal_sequence
```

Each scenario asserts selected per-line trace fields. On failure the report keeps
the complete authoritative trace and adds a `minimal_failure.lines` candidate
produced by delta debugging. It also emits a `minimal_regression_case` object
that can be promoted into a fixture after review. The shrinker only deletes commands and must preserve
the same field-level mismatch; it never changes gate pass/fail evidence.
## Finite-state and metamorphic checks

`run_product_model_check.py` exhaustively explores every canonical
`PaperBtAckState` and event transition, then checks safety invariants such as
mutually exclusive armed/pending/running phases, disconnect behavior, and
idempotent busy/realtime events. It exhaustively checks small paper-search
sensor/deadline/step-limit combinations and their terminal-decision invariant.
It also applies case, whitespace, line-number,
and comment transformations to protocol inputs while preserving the expected
motion classification.

```powershell
$env:GRBL_ROOT='D:\Users\Grbl_Esp32'
python native_sim/run_product_model_check.py
```

The report is written to `native_sim/results/product_model_check.json` and is a
hard `native_model` layer in the standard Agent gate. This bounded exploration
finds reducer and classification defects; it does not model FreeRTOS scheduling,
Bluetooth transport timing, or physical paper mechanics. The Python Paper Plant
is a separate deterministic mechanical model and does not execute the complete
eight-stage firmware controller.
## QWEN / Xiaozhi evidence adapter

QWEN remains the owner of its pytest, FakeDevice, firmware contract, and drawing
E2E tests. `fz` only orchestrates fixed targets and stores the result as evidence:

```powershell
$env:QWEN_ROOT='D:\QWEN3.0'
python scripts/qwen_evidence_adapter.py --profile standard
```

This does not copy a simulation engine into QWEN and does not replace `fz`
protocol/hardware SIL or paper/BT HIL. The MCP surface exposes the same fixed
profiles through `list_qwen_profiles` and `run_qwen_gate`.
