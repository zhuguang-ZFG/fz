# Paper firmware and Plant contract

## Problem

The deterministic Plant intentionally runs faster and at a coarser abstraction
than the real product. Before this contract, those differences were duplicated
as unexplained Python constants. A firmware change could therefore leave the PC
simulation green while silently changing the real timeout, debounce policy, or
travel limits.

The concrete discrepancy found during review was:

- firmware `PAPER_SENSOR_TIMEOUT_MS`: 15000 ms;
- Plant `timeout_ms`: 2500 ms.

The acceleration is useful under virtual testing, but it must be declared and
checked rather than mistaken for product equality.

## Decision

Maintain a small reviewed machine-readable dictionary in
`hardware_sim/paper_firmware_contract.json`. The validator reads fixed product
source paths under `GRBL_ROOT`, extracts numeric preprocessor definitions, and
checks both exact firmware snapshots and declared Plant abstractions.

Supported abstraction contracts initially include:

- exact Plant values;
- rational scaling from one firmware constant;
- sensor threshold abstraction from firmware sample/threshold constants.

Any firmware or Plant drift is a hard gate failure. Updating the dictionary is
an explicit review action, not an automatic baseline rewrite.

## Community and official patterns

- Espressif pytest-embedded composes target-specific services around a shared
  test contract. This layer similarly keeps product-source validation separate
  from mechanical Plant execution and HIL.
- NASA F´ uses models and generated dictionaries to keep flight-software
  interfaces and ground/test tooling synchronized. The reviewed JSON dictionary
  serves the same consistency role at smaller scope.
- Renode emphasizes deterministic execution of production artifacts and
  reproducible test metadata. The report records product root, observed firmware
  constants, observed Plant values, and exact violations.
- Zephyr Twister separates platform data, test plans, harnesses, and reports.
  This is therefore an independent `paper_contract` gate layer rather than an
  implicit assertion buried inside one Plant scenario.

## Evidence boundary

The contract proves that declared source constants and simulation abstractions
remain synchronized. It does not prove that the constants are physically
calibrated, that paper friction follows the model, or that hardware timing and
HIL acceptance pass.

## Sources

- https://github.com/espressif/pytest-embedded
- https://github.com/nasa/fprime
- https://github.com/renode/renode
- https://github.com/zephyrproject-rtos/zephyr
