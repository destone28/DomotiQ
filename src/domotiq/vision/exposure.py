# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The light of the webcam followed in small damped steps, while the house looks.

The calibration finds exposure, white balance and gain on the empty house (camera.tune) and locks them. When the
light of the hall changes, this follows it: every MEASURE_S of time the brightness of the probe (the driveway and the
strip around the house, where the lights of the house do not reach) is compared with the same place in the empty
house in use, and outside the band one step of the gain brings it back, most of the way. The white balance is not
touched, and the full setting of the webcam (9-10 s without pictures) is left for when this cannot follow.

Measured on the C270 of casa1 (8 October), which the numbers below come from:
- the exposure goes in steps: the longest real one is 350-675 (0.1 ms; 625 is used), and beyond the time of a frame
  (67 ms at 15 fps) the picture is only multiplied, x2 x3 x4, at the same 15 fps. Even with every light of the hall
  on, 625 with no gain gives 16 of 255: shorter exposures are of no use there. So the gain moves, and the exposure
  only goes one real step down (x0.32-0.40) when the gain is at its floor and the picture still too bright;
- the gain does nothing from 0 to 8, jumps x2.2 at 12, and from there rises smoothly: one unit is +8-14% of light on
  the probe below 24, +3% from 24 to 48, +1% from 48 to 96, +0.2-0.4% above 128. As light ∝ gain^k, k went from 0.25
  to 1.8 depending on the gain and the scene: k is measured on the last two points, the table only starts it;
- a new gain shows in the next frame, a new exposure two frames later;
- still for a minute, the probe moves by 0.2-0.7% (deviation), 0.9-2.9% at most; daylight went down 14% in a quarter
  of an hour: the band is BAND around the empty house, the steps at most CAP each.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

MEASURE_S = 0.5          # time between two looks, not frames: with long exposures the frames slow down
BAND = 0.05              # within 5% of the empty house in use nothing is touched (the light moves 1-3% by itself)
DAMP = 0.8               # each step goes this share of the way: the response of the scene is measured, and noisy
CAP = 0.08               # and changes the light by at most 8%: the light changing by 12% in 2 s is a change of the
                         # hall for the house (D-66), the steps of the webcam must not look like one
K_MIN, K_MAX = 0.25, 2.5           # where the measured response is believed (1.8 measured on the probe at the lowest
                                   # gains, steeper scenes can be); beyond, the scene changed between the two looks
GAIN_FLOOR, GAIN_MAX = 12, 255     # below 12 the gain of the C270 does nothing
EXPOSURES = (625, 312, 156, 78)    # the real steps of the exposure, longest first
EXPOSURE_STEP = 0.36               # one of them down gives this much of the light (measured 0.32-0.40)
NOISE_EXP = 0.6                    # the noise of a pixel grows as its brightness^0.6 when the gain rises
HOUR_S = 3600.0


# the light of the probe against the gain, at the longest exposure, relative to gain 32: casa1 with the light of the
# hall at half and at most (8 October), their geometric mean. Only a start: k is measured on the scene
GAIN_LIGHT = ((12, 0.288), (16, 0.444), (24, 0.769), (32, 1.0), (40, 1.257), (48, 1.501), (64, 1.839), (80, 2.159),
              (96, 2.386), (128, 2.852), (160, 3.183), (192, 3.445), (255, 3.846))


def gain_light(gain: float) -> float:
    """How much light the gain gives, from GAIN_LIGHT (log-log in between)."""
    g = min(max(float(gain), GAIN_LIGHT[0][0]), GAIN_LIGHT[-1][0])
    for (g0, l0), (g1, l1) in zip(GAIN_LIGHT, GAIN_LIGHT[1:]):
        if g <= g1:
            t = math.log(g / g0) / math.log(g1 / g0)
            return math.exp(math.log(l0) + t * (math.log(l1) - math.log(l0)))
    return GAIN_LIGHT[-1][1]


def gain_for(light: float) -> int:
    """The gain that gives this much light (the inverse of gain_light), within the limits."""
    return min(range(GAIN_FLOOR, GAIN_MAX + 1), key=lambda g: abs(math.log(gain_light(g) / max(light, 1e-6))))


def prior_k(gain: int) -> float:
    """The response of the probe to the gain around this gain, from the table (light ∝ gain^k)."""
    lo, hi = max(GAIN_FLOOR, gain / 1.25), min(GAIN_MAX, gain * 1.25)
    return min(K_MAX, max(K_MIN, math.log(gain_light(hi) / gain_light(lo)) / math.log(hi / lo)))


@dataclass
class CameraStep:
    gain: int
    exposure: int
    factor: float        # the brightness expected after the step, over the one before
    ratio: float         # how bright the probe was, against the empty house in use
    uncertain: bool      # the exposure changed: the factor is a guess, the light of the rooms is measured again


class GainRegulator:
    """Decides the steps; the webcam is set by whoever owns it (the vision process), which then says it is done."""

    def __init__(self, gain: int, exposure: int = EXPOSURES[0]) -> None:
        self.gain, self.exposure = int(gain), int(exposure)
        self._next = 0.0
        self._last: tuple[int, int, float] | None = None   # gain, exposure and probe ratio of the last look
        self._k: float | None = None
        self.ratio: float | None = None
        self.paused = ""
        self.at_limit = False
        self.settled = False                 # as close as the steps of the webcam allow, though outside the band
        self.waiting = False                 # a step asked and not yet seen in the pictures
        self._steps: deque[tuple[float, int]] = deque()   # when, and which way
        self._way = 0                        # which way the last step went, while nothing else happened
        self.last_step: dict | None = None

    # ------------------------------------------------------------ what the house knows
    def set(self, gain: int, exposure: int) -> None:
        """The webcam has these values now (a start, a full setting): what was measured before says nothing."""
        self.gain, self.exposure = int(gain), int(exposure)
        self._last, self._k, self.waiting, self.at_limit, self._way = None, None, False, False, 0

    def pause(self, why: str) -> None:
        self.paused = why
        self._last, self._way = None, 0      # what is seen after a pause may be another scene

    def due(self, now: float) -> bool:
        return not self.waiting and now >= self._next

    def done(self, step: CameraStep, now: float) -> None:
        """The step is in the pictures from now on."""
        self.waiting = False
        self._next = now + MEASURE_S

    def failed(self) -> None:
        self.waiting = False

    # ------------------------------------------------------------ one look
    def consider(self, ratio: float, now: float) -> CameraStep | None:
        """The probe is `ratio` times as bright as in the empty house in use: a step, if it is outside the band."""
        self.paused = ""
        self._next = now + MEASURE_S
        self.ratio = ratio
        last, self._last = self._last, (self.gain, self.exposure, ratio)
        if last is not None and last[1] == self.exposure and last[0] != self.gain and last[2] > 0 and ratio > 0:
            span = math.log(self.gain / last[0])
            if abs(span) > 0.05:
                k = math.log(ratio / last[2]) / span
                if k > 0:
                    self._k = min(K_MAX, max(K_MIN, k))
        off = abs(math.log(max(ratio, 1e-3)))
        self.settled = False
        if off <= math.log(1.0 + BAND):
            self.at_limit = False
            return None
        way = 1 if ratio < 1.0 else -1
        if way == -self._way and off < 2 * math.log(1.0 + BAND):
            # the last step crossed the band: one unit of gain is more than the band here (at the lowest gains one
            # unit is 8-14% of the light), and going back would cross it again. As close as the webcam can get
            self.at_limit, self.settled = False, True
            return None
        cap = math.log(1.0 + CAP)
        want = max(-cap, min(cap, DAMP * math.log(1.0 / max(ratio, 1e-3))))   # in log of the light
        k = self._k or prior_k(self.gain)
        ideal = self.gain * math.exp(want / k)
        # rounded towards the gain of now, so that the step stays within the cap; outside the band at least one unit
        # the right way (at the lowest gains one unit is already 8-14% of the light: the smallest step there is)
        gain = math.floor(ideal) if want > 0 else math.ceil(ideal)
        if gain == self.gain:
            gain += 1 if want > 0 else -1
        gain = max(GAIN_FLOOR, min(GAIN_MAX, gain))
        exposure = self.exposure
        if gain == self.gain:
            step = self._exposure_step(want)
            if step is None:
                self.at_limit = True
                return None
            gain, exposure = step
        self.at_limit = False
        if exposure == self.exposure:
            factor = (gain / self.gain) ** k
            if abs(math.log(max(ratio * factor, 1e-3))) >= off:
                self.settled = True          # one unit would land farther from the empty house than now
                return None
        else:
            levels = EXPOSURES.index(exposure) - EXPOSURES.index(self.exposure)
            factor = EXPOSURE_STEP ** levels * gain_light(gain) / gain_light(self.gain)
        step = CameraStep(gain, exposure, factor, ratio, exposure != self.exposure)
        self._record(step, now)
        return step

    def _exposure_step(self, want: float) -> tuple[int, int] | None:
        """At the end of the gain: one real step of the exposure, the gain set again to keep the light about where it
        was going. None at the very end (the brightest or darkest the webcam can do)."""
        i = EXPOSURES.index(self.exposure) if self.exposure in EXPOSURES else 0
        if want < 0 and self.gain <= GAIN_FLOOR and i + 1 < len(EXPOSURES):
            # the gain makes up for the shorter exposure
            return gain_for(gain_light(self.gain) * math.exp(want) / EXPOSURE_STEP), EXPOSURES[i + 1]
        if want > 0 and i > 0:
            # the longer exposure gives more than needed: less gain
            return gain_for(gain_light(self.gain) * math.exp(want) * EXPOSURE_STEP), EXPOSURES[i - 1]
        return None

    def _record(self, step: CameraStep, now: float) -> None:
        self.waiting = True
        way = 1 if step.factor > 1 else -1
        self._way = 0 if step.uncertain else way      # after a guess, a correction the other way is no seesaw
        self._steps.append((now, way))
        while self._steps and now - self._steps[0][0] > HOUR_S:
            self._steps.popleft()
        self.last_step = {"t": round(now, 1), "gain": [self.gain, step.gain], "exposure": [self.exposure, step.exposure],
                          "ratio": round(step.ratio, 3), "factor": round(step.factor, 3)}
        if step.exposure != self.exposure:
            self._last, self._k = None, None  # another response from here
        self.gain, self.exposure = step.gain, step.exposure

    # ------------------------------------------------------------ diagnostics
    def status(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        steps = [d for t, d in self._steps if now - t <= HOUR_S]
        return {"gain": self.gain, "exposure": self.exposure,
                "ratio": round(self.ratio, 3) if self.ratio is not None else None,
                "band": BAND, "steps_hour": len(steps),
                "reversals_hour": sum(1 for a, b in zip(steps, steps[1:]) if a != b),
                "last": self.last_step, "paused": self.paused, "at_limit": self.at_limit, "settled": self.settled}
