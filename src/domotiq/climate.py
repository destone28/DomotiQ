# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The virtual climate: a thermostat you warm with a finger, a shower you breathe on.

The fair hall has no fixed temperature, so thresholds are relative to a
moving baseline: the average of the last few minutes. A finger on the
sensor raises it slowly (the board has thermal mass), a breath raises the
humidity in a second or two; either one counts.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Baseline:
    window_s: float = 300.0
    samples: deque = field(default_factory=deque)

    def add(self, ts: float, value: float) -> None:
        self.samples.append((ts, value))
        while self.samples and ts - self.samples[0][0] > self.window_s:
            self.samples.popleft()

    def value(self) -> float | None:
        if not self.samples:
            return None
        return sum(v for _, v in self.samples) / len(self.samples)

    def rate(self, seconds: float = 10.0) -> float:
        """Slope over the last `seconds`, in units per second."""
        if len(self.samples) < 2:
            return 0.0
        t_end, v_end = self.samples[-1]
        for t, v in self.samples:
            if t_end - t <= seconds:
                if t_end - t < 1.0:
                    return 0.0
                return (v_end - v) / (t_end - t)
        return 0.0


class Thermostat:
    """normal → hot when warmed or breathed on, cold when cooled down."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.temp = Baseline(cfg.get("baseline_s", 300))
        self.rh = Baseline(cfg.get("baseline_s", 300))
        self.state = "normal"
        self.frozen_temp: float | None = None
        self.frozen_rh: float | None = None

    def update(self, ts: float, temp: float, rh: float) -> str | None:
        """Add a reading; return the new state when it changes."""
        base_t = self.frozen_temp if self.state != "normal" else self.temp.value()
        base_rh = self.frozen_rh if self.state != "normal" else self.rh.value()
        new = self.state
        if base_t is not None and base_rh is not None:
            hot = (temp - base_t >= self.cfg["hot_delta"]
                   or self.temp.rate() >= self.cfg["hot_rate"]
                   or rh - base_rh >= self.cfg["breath_rh_delta"])
            cold = base_t - temp >= self.cfg["cold_delta"]
            calm = (abs(temp - base_t) <= self.cfg["release_delta"]
                    and rh - base_rh < self.cfg["breath_rh_delta"] / 2)
            if self.state == "normal":
                if hot:
                    new = "hot"
                elif cold:
                    new = "cold"
            elif calm:
                new = "normal"
        if new != self.state:
            if new != "normal":
                # keep the baseline of before the finger, or it would chase the warm reading
                self.frozen_temp, self.frozen_rh = base_t, base_rh
            else:
                self.frozen_temp = self.frozen_rh = None
            self.state = new
            if new == "normal":
                self.temp.add(ts, temp)
                self.rh.add(ts, rh)
            return new
        if self.state == "normal":
            self.temp.add(ts, temp)
            self.rh.add(ts, rh)
        return None


class Shower:
    """Bathroom humidity: someone is having a shower."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.rh = Baseline(cfg.get("baseline_s", 300))
        self.on = False
        self.frozen: float | None = None

    def update(self, ts: float, rh: float) -> str | None:
        base = self.frozen if self.on else self.rh.value()
        if base is None:
            self.rh.add(ts, rh)
            return None
        if not self.on and rh - base >= self.cfg["shower_rh_delta"]:
            self.on, self.frozen = True, base
            return "start"
        if self.on and rh - base <= self.cfg["shower_release"]:
            self.on, self.frozen = False, None
            self.rh.add(ts, rh)
            return "stop"
        if not self.on:
            self.rh.add(ts, rh)
        return None
