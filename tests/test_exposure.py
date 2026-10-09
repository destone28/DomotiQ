# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The light of the webcam followed in small damped steps of the gain (vision/exposure.py)."""

from __future__ import annotations

import math
import random

import pytest

from domotiq.vision.exposure import (BAND, CAP, EXPOSURES, GAIN_FLOOR, GAIN_MAX, GainRegulator, gain_light,
                                     MEASURE_S)


def scene(c: float, k: float):
    """A probe whose light is c times the empty house at gain 32, answering the gain as light ∝ gain^k around the
    measured curve (k bends it: 1 is the curve of casa1)."""
    def light(gain: int, exposure: int) -> float:
        g = gain_light(gain) ** k
        e = 0.36 ** EXPOSURES.index(exposure) if exposure in EXPOSURES else 1.0
        return c * g * e
    return light


def follow(light, gain=32, exposure=625, looks=30, noise=0.0, seed=1):
    """Look every MEASURE_S, step when asked; returns the ratios seen and the regulator."""
    rng = random.Random(seed)
    reg = GainRegulator(gain, exposure)
    t, seen = 100.0, []
    for _ in range(looks):
        ratio = light(reg.gain, reg.exposure) * (1.0 + rng.uniform(-noise, noise))
        seen.append(ratio)
        before = reg.gain
        step = reg.consider(ratio, t)
        if step is not None:
            single = abs(step.gain - before) == 1           # the smallest step the gain has
            assert abs(math.log(step.factor)) <= math.log(1.0 + CAP) + 1e-6 or step.uncertain or single, step
            reg.done(step, t + 0.15)
        t += MEASURE_S
    return seen, reg


def reversals(seen):
    sides = [1 if r > 1 + BAND else -1 if r < 1 - BAND else 0 for r in seen]
    sides = [s for s in sides if s]
    return sum(1 for a, b in zip(sides, sides[1:]) if a != b)


@pytest.mark.parametrize("k", [0.25, 0.4, 0.7, 1.0, 1.4, 1.8])
@pytest.mark.parametrize("start", ["dark", "bright"])
def test_the_light_is_followed_into_the_band_or_to_a_limit(k, start):
    """From the dark (a third of the light) and from full light (three times): into the band, or stopped at a limit
    of the webcam, crossing the band at most once, every step within the cap."""
    c = 0.33 if start == "dark" else 3.0
    seen, reg = follow(scene(c, k), looks=40)
    inside = abs(math.log(seen[-1])) <= math.log(1 + BAND)
    at_end = reg.at_limit and (reg.gain in (GAIN_FLOOR, GAIN_MAX))
    closest = reg.settled and abs(math.log(seen[-1])) <= 2 * math.log(1 + BAND)   # one unit of gain is more than the band
    assert inside or at_end or closest, (k, start, [round(r, 2) for r in seen], reg.gain, reg.exposure)
    assert reversals(seen) <= 1, (k, start, [round(r, 2) for r in seen])


def test_the_flicker_of_the_light_makes_no_seesaw():
    """The light moves by itself by a couple of percent (measured 0.9-2.9% in a still minute): once in the band,
    nothing is touched."""
    seen, reg = follow(scene(1.0, 1.0), looks=200, noise=0.03)
    assert reg.status(100.0 + 200 * MEASURE_S)["steps_hour"] == 0


def test_a_slow_evening_is_followed_with_few_steps():
    """Daylight went down 14% in a quarter of an hour on casa1: a few steps, one way."""
    reg = GainRegulator(32)
    t, steps, light = 0.0, 0, scene(1.0, 1.0)
    while t < 900:
        hall = 1.0 - 0.14 * t / 900
        step = reg.consider(light(reg.gain, reg.exposure) * hall, t)
        if step is not None:
            steps += 1
            reg.done(step, t + 0.15)
        t += MEASURE_S
    st = reg.status(t)
    assert 1 <= steps <= 4 and st["reversals_hour"] == 0, (steps, st)


def test_too_bright_at_the_lowest_gain_one_real_step_of_the_exposure():
    """A hall much brighter than casa1 (a sunny fair): the gain reaches its floor, then the exposure goes one real
    step down and the gain makes up for it; the step says its factor is a guess."""
    seen, reg = follow(scene(8.0, 1.0), looks=60)
    assert reg.exposure < EXPOSURES[0]
    assert abs(math.log(seen[-1])) <= math.log(1 + BAND) or reg.at_limit


def test_in_the_dark_it_stops_at_the_highest_gain():
    seen, reg = follow(scene(0.05, 1.0), looks=60)
    assert reg.gain == GAIN_MAX and reg.at_limit and reg.exposure == EXPOSURES[0]


def test_one_look_every_half_second_of_time_however_many_frames():
    """Two frames a second or fifteen: the light is looked at by the clock, and never twice before a step shows."""
    reg = GainRegulator(32)
    assert reg.due(0.0)
    step = reg.consider(0.5, 0.0)
    assert step is not None and not reg.due(0.2) and not reg.due(5.0)    # waiting for the step to show
    reg.done(step, 0.2)
    assert not reg.due(0.5) and reg.due(0.71)


def test_a_reconnection_puts_back_the_values_reached_not_those_of_the_calibration():
    from domotiq.vision.camera import current_values, lock_key
    stored = {"exposure": 625, "wb": 6250, "gain": 32, "balance": [1.1, 1.0, 0.9]}
    now = {"exposure": 625, "gain": 47, "lock": lock_key(stored)}
    assert current_values(stored, now)["gain"] == 47
    # values reached from another calibration are void: the new one counts
    assert current_values(dict(stored, gain=64), now)["gain"] == 64
    assert current_values(stored, None)["gain"] == 32


def test_when_the_frames_stop_back_to_the_calibration():
    from domotiq.vision.camera import back_to_calibration
    stored = {"exposure": 625, "wb": 6250, "gain": 32, "balance": [1.1, 1.0, 0.9]}
    assert back_to_calibration(stored, 200, 625) == {"gain": 32, "exposure": 625}
    assert back_to_calibration(stored, 32, 625) is None
    assert back_to_calibration(None, 200, 625) is None
