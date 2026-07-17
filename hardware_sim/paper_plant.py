#!/usr/bin/env python3
"""Deterministic paper transport plant and safety controller for host simulation."""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(order=True)
class ScheduledEvent:
    at_ms: int
    sequence: int
    callback: Callable[[], None] = field(compare=False)


class VirtualClock:
    def __init__(self) -> None:
        self.now_ms = 0
        self._sequence = 0
        self._events: List[ScheduledEvent] = []

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        if delay_ms < 0:
            raise ValueError("delay_ms must be non-negative")
        self._sequence += 1
        heapq.heappush(self._events, ScheduledEvent(self.now_ms + delay_ms, self._sequence, callback))

    def run(self, deadline_ms: int) -> None:
        while self._events and self._events[0].at_ms <= deadline_ms:
            event = heapq.heappop(self._events)
            self.now_ms = event.at_ms
            event.callback()
        self.now_ms = deadline_ms


@dataclass(frozen=True)
class PaperPlantConfig:
    tick_ms: int = 10
    feed_speed_mm_s: float = 50.0
    sensor_position_mm: float = 40.0
    overtravel_mm: float = 20.0
    timeout_ms: int = 2500
    debounce_samples: int = 4
    minimum_sensor_travel_mm: float = 5.0
    lower_bound_mm: float = -2.0


@dataclass(frozen=True)
class FaultProfile:
    name: str = "none"
    paper_present: bool = True
    speed_scale: float = 1.0
    jam_at_mm: Optional[float] = None
    sensor_stuck: Optional[bool] = None
    sensor_bounce_samples: int = 0
    reverse: bool = False


@dataclass
class PaperPlantState:
    position_mm: float = 0.0
    motor_on: bool = False
    sensor_active: bool = False
    jammed: bool = False


class PaperTransportSimulation:
    def __init__(self, config: PaperPlantConfig, fault: FaultProfile) -> None:
        self.config = config
        self.fault = fault
        self.clock = VirtualClock()
        self.plant = PaperPlantState()
        self.controller_state = "idle"
        self.outcome = "running"
        self.reason = ""
        self.sensor_stable_count = 0
        self.detected_position_mm: Optional[float] = None
        self.finished_at_ms: Optional[int] = None
        self.transitions: List[Dict[str, Any]] = []
        self.covered: set[str] = set()
        self._bounce_remaining = fault.sensor_bounce_samples

    def _record(self, event: str, **details: Any) -> None:
        self.transitions.append(
            {
                "at_ms": self.clock.now_ms,
                "event": event,
                "controller_state": self.controller_state,
                "position_mm": round(self.plant.position_mm, 3),
                "sensor_active": self.plant.sensor_active,
                **details,
            }
        )

    def start(self) -> None:
        self.controller_state = "feeding"
        self.plant.motor_on = True
        self.covered.add("motor_start")
        self._record("start")
        self.clock.schedule(self.config.tick_ms, self._tick)
        self.clock.run(self.config.timeout_ms + self.config.tick_ms)
        if self.outcome == "running":
            self._finish("failed", "scheduler_exhausted")

    def _raw_sensor(self) -> bool:
        if self.fault.sensor_stuck is not None:
            self.covered.add("sensor_stuck")
            return self.fault.sensor_stuck
        active = self.fault.paper_present and self.plant.position_mm >= self.config.sensor_position_mm
        if active and self._bounce_remaining > 0:
            self.covered.add("sensor_bounce")
            self._bounce_remaining -= 1
            return self._bounce_remaining % 2 == 0
        return active

    def _tick(self) -> None:
        if self.outcome != "running":
            return
        elapsed_s = self.config.tick_ms / 1000.0
        if self.plant.motor_on:
            direction = -1.0 if self.fault.reverse else 1.0
            if self.fault.reverse:
                self.covered.add("motor_reverse")
            if self.fault.jam_at_mm is not None and self.plant.position_mm >= self.fault.jam_at_mm:
                self.plant.jammed = True
                self.covered.add("motor_jam")
            if not self.plant.jammed:
                delta = self.config.feed_speed_mm_s * self.fault.speed_scale * elapsed_s * direction
                self.plant.position_mm += delta
                if self.fault.speed_scale < 1.0:
                    self.covered.add("paper_slip")
        self.plant.sensor_active = self._raw_sensor()
        self._controller_step()
        if self.outcome == "running":
            self.clock.schedule(self.config.tick_ms, self._tick)

    def _controller_step(self) -> None:
        if self.plant.position_mm < self.config.lower_bound_mm:
            self.covered.add("reverse_bound_check")
            self._finish("failed", "reverse_motion")
            return
        if self.clock.now_ms >= self.config.timeout_ms:
            self.covered.add("timeout")
            self._finish("failed", "timeout")
            return
        if self.controller_state == "feeding":
            if self.plant.sensor_active and self.plant.position_mm < self.config.minimum_sensor_travel_mm:
                self.covered.add("sensor_plausibility")
                self._finish("failed", "sensor_active_too_early")
                return
            self.sensor_stable_count = self.sensor_stable_count + 1 if self.plant.sensor_active else 0
            if self.sensor_stable_count >= self.config.debounce_samples:
                self.detected_position_mm = self.plant.position_mm
                self.controller_state = "overtravel"
                self.covered.add("sensor_debounce")
                self._record("sensor_confirmed")
        elif self.controller_state == "overtravel":
            assert self.detected_position_mm is not None
            if self.plant.position_mm - self.detected_position_mm >= self.config.overtravel_mm:
                self.covered.add("overtravel_complete")
                self._finish("completed", "paper_positioned")

    def _finish(self, outcome: str, reason: str) -> None:
        self.outcome = outcome
        self.reason = reason
        self.finished_at_ms = self.clock.now_ms
        self.plant.motor_on = False
        self.controller_state = "complete" if outcome == "completed" else "failed"
        self.covered.add("motor_stop")
        self._record("finish", outcome=outcome, reason=reason)

    def report(self) -> Dict[str, Any]:
        return {
            "fault": self.fault.name,
            "outcome": self.outcome,
            "reason": self.reason,
            "virtual_duration_ms": self.finished_at_ms if self.finished_at_ms is not None else self.clock.now_ms,
            "final_position_mm": round(self.plant.position_mm, 3),
            "covered": sorted(self.covered),
            "transitions": self.transitions,
        }


def simulate(config: PaperPlantConfig, fault: FaultProfile) -> Dict[str, Any]:
    simulation = PaperTransportSimulation(config, fault)
    simulation.start()
    return simulation.report()
