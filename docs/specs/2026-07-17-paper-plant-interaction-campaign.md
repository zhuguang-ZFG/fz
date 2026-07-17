# Paper Plant interaction campaign

## Decision

The next no-board simulation layer is bounded combinatorial model checking,
not another hand-written fault profile. The existing named campaign remains the
readable acceptance suite. A separate interaction campaign exhausts the small
paper-plant factor space and fails the Agent gate on safety-property violations.

## Community and industry patterns

- Microsoft PICT generates compact pairwise configuration suites. The paper
  model has only 48 configurations, so exhaustive enumeration is cheaper and
  stronger than reducing the suite to pairwise rows.
- Hypothesis checks properties over generated inputs and reports a simplest
  counterexample. This campaign uses deterministic enumeration and reports the
  lowest-complexity failing configuration as `minimal_failure`.
- Renode emphasizes deterministic virtual execution and reproducible test
  artifacts. Wokwi CI similarly combines bounded execution, explicit failure
  criteria, scenarios, and logs. The campaign therefore uses virtual time and a
  structured JSON report rather than wall-clock timing or process exit alone.
- Zephyr Twister separates test plans, harnesses, reports, quarantine, and
  hardware maps. The interaction campaign is an independent hard-gate layer so
  it does not blur the named acceptance suite or HIL evidence.

## Bounded model

Factors:

- paper: present / missing
- speed: normal / 40% slip
- drive: normal / jam / reverse
- sensor: normal / bounce / stuck inactive / stuck active

The Cartesian product contains 48 configurations and 44 distinct pairwise
value interactions. Every configuration runs twice and must satisfy:

1. identical deterministic replay;
2. terminal completed/failed outcome with a known reason;
3. motor stopped and final transition recorded;
4. completion only for present paper, normal drive, and normal/bouncing sensor.

## Evidence boundary

This is bounded deterministic mechanical/sensor evidence. It does not prove
ESP32 scheduling, motor torque, the real paper-friction distribution, Bluetooth
transport, electrical behavior, or HIL acceptance.

## Sources

- https://github.com/microsoft/pict
- https://github.com/HypothesisWorks/hypothesis
- https://github.com/renode/renode
- https://github.com/wokwi/wokwi-ci-action
- https://github.com/zephyrproject-rtos/zephyr
