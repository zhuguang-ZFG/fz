# Paper transient fault campaign

## Problem

Static fault profiles and Cartesian combinations cannot represent faults that
appear and recover during one operation. Real paper mechanisms can briefly
stall, lose a sensor signal, or slow under changing load. Treating each as a
permanent fault overestimates some failures and misses recovery defects.

## Decision

Add typed virtual-time fault windows to the deterministic Paper Plant:

- `jam`: motor motion pauses only while the window is active;
- `sensor`: raw sensor state is forced inactive or active;
- `speed_scale`: feed speed is multiplied by a bounded value from 0 to 1.

Windows use `[start_ms, end_ms)` semantics and are evaluated before each Plant
tick. Overlapping windows of the same kind are rejected so precedence is never
implicit. Different kinds may overlap to model composed incidents.

The fixed hard-gate campaign covers:

1. brief jam recovery;
2. persistent jam fail-closed timeout;
3. temporary sensor dropout recovery;
4. early false-active sensor rejection;
5. temporary speed degradation recovery;
6. sequential jam plus sensor dropout recovery.

Every scenario is replayed twice. Failing scenarios shrink one selected window
from both edges until removing another tick would change the failure outcome or
reason. The artifact is a tick-granularity local minimum, not a claim of a
globally minimal physical fault.

## Community and official patterns

- CNCF Chaos Mesh models managed, scheduled fault experiments and separates
  scenario definition from orchestration and evidence.
- Renode external control and Robot scenarios inject events against a
  deterministic virtual platform.
- Hypothesis demonstrates automatic reduction of failures to simpler
  counterexamples. This campaign applies deterministic boundary shrinking to
  virtual-time windows.
- Wokwi CI uses bounded scenarios, explicit expected/failure criteria, and log
  artifacts. The transient runner similarly emits a structured report rather
  than relying on process exit alone.

## Evidence boundary

This layer validates deterministic mechanical/sensor timing scenarios. It does
not emulate ESP32 task scheduling, ISR latency, contact bounce waveforms,
electrical transients, Bluetooth timing, motor torque, or HIL behavior.

## Sources

- https://github.com/chaos-mesh/chaos-mesh
- https://github.com/renode/renode
- https://github.com/HypothesisWorks/hypothesis
- https://github.com/wokwi/wokwi-ci-action
