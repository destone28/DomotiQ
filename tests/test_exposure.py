# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The light of the webcam followed in small damped steps of the gain (vision/exposure.py)."""

from __future__ import annotations

import math
import random

import pytest

from domotiq.vision.exposure import (BAND, CAP, CAP_ADAPT, DIGITAL, EXPOSURES, GAIN_FLOOR, GAIN_MAX, LADDER,
                                     GainRegulator, exposure_light, gain_light, MEASURE_S)


def scene(c: float, k: float):
    """Rooms whose light is c times the empty house at gain 32, answering the gain as light ∝ gain^k around the
    measured curve (k bends it: 1 is the curve of casa1)."""
    def light(gain: int, exposure: int) -> float:
        g = gain_light(gain) ** k
        return c * g * exposure_light(exposure)
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
    """A room much brighter than casa1 (in the sun): the gain reaches its floor, then the exposure goes one real
    step down and the gain makes up for it; the step says its factor is a guess."""
    seen, reg = follow(scene(8.0, 1.0), looks=60)
    assert reg.exposure < EXPOSURES[0]
    assert abs(math.log(seen[-1])) <= math.log(1 + BAND) or reg.at_limit


def test_in_the_dark_it_stops_at_the_highest_gain():
    seen, reg = follow(scene(0.05, 1.0), looks=80)
    assert reg.gain == GAIN_MAX and reg.at_limit and reg.exposure == LADDER[0] and reg.at_dark_end


def test_a_hall_darker_than_the_gain_can_make_up_takes_the_digital_light_at_the_highest_gain():
    """10 October: brightness 22 of 50 at gain 255 and exposure 625. Beyond it the webcam multiplies its pictures
    (x1.7 to x2.9): taken only with the gain at its highest, and given back first when the hall gets lighter."""
    seen, reg = follow(scene(0.15, 1.0), looks=80)
    assert reg.exposure in DIGITAL and reg.gain == GAIN_MAX
    assert abs(math.log(seen[-1])) <= math.log(1 + 0.3)              # back near the empty house
    light = {"c": 0.15}
    seen, reg2 = [], GainRegulator(reg.gain, reg.exposure)
    t = 200.0
    for _ in range(60):                                             # the hall lit again, three times as much
        ratio = 0.45 * gain_light(reg2.gain) * exposure_light(reg2.exposure)
        step = reg2.consider(ratio, t)
        if step is not None:
            assert not (step.gain < GAIN_MAX and step.exposure in DIGITAL), step   # never digital light with less gain
            reg2.done(step, t + 0.15)
        seen.append(ratio)
        t += MEASURE_S
    assert reg2.exposure not in DIGITAL and abs(math.log(seen[-1])) <= math.log(1 + BAND) + 0.02


def test_one_look_every_half_second_of_time_however_many_frames():
    """Two frames a second or fifteen: the light is looked at by the clock, and never twice before a step shows."""
    reg = GainRegulator(32)
    assert reg.due(0.0)
    step = reg.consider(0.5, 0.0)
    assert step is not None and not reg.due(0.2) and not reg.due(5.0)    # waiting for the step to show
    reg.done(step, 0.2)
    assert not reg.due(0.5) and reg.due(0.71)


def test_a_step_that_landed_in_the_band_is_no_reason_to_hold_later():
    """casa1, 9 October: a step down, then the evening took the light 7% below the empty house, the other way. That is
    no seesaw: the step had landed in the band. It was held for minutes, as if one unit of gain were too much."""
    reg = GainRegulator(154)
    step = reg.consider(1.12, 0.0)
    assert step is not None and step.gain < 154
    reg.done(step, 0.2)
    assert reg.consider(1.01, 1.0) is None                  # in the band
    before = reg.gain
    step = reg.consider(0.93, 2.0)                          # the evening, the other way
    assert step is not None and step.gain > before and not reg.settled


def test_a_step_across_the_band_is_still_held_where_one_unit_is_too_much():
    reg = GainRegulator(13)
    step = reg.consider(1.07, 0.0)                          # one unit down at the bottom of the gain: -12%
    assert step is not None and step.gain == 12
    reg.done(step, 0.2)
    assert reg.consider(0.94, 1.0) is None and reg.settled  # back up would cross the band again


def test_another_empty_house_forgets_the_last_look():
    """The empty house compared with changed: what was seen before says nothing of the response of the gain, and a
    step the other way is no seesaw."""
    reg = GainRegulator(13)
    reg.done(reg.consider(1.07, 0.0), 0.2)
    reg.target_changed()
    assert reg.consider(0.90, 1.0) is not None


def test_while_the_house_follows_a_change_of_the_hall_the_steps_are_larger():
    reg = GainRegulator(32)
    small = reg.consider(0.5, 0.0)
    reg = GainRegulator(32)
    large = reg.consider(0.5, 0.0, CAP_ADAPT)
    assert small.factor <= 1 + CAP + 1e-6 and 1 + CAP < large.factor <= 1 + CAP_ADAPT + 1e-6, (small, large)


def test_below_the_floor_of_the_gain_the_steps_come_from_the_table():
    """In a very bright hall the full setting chooses gain 0: from there one unit does nothing, the first step up is
    gain 12 (x2.2 measured), taken only if it lands closer to the empty house; down, only the exposure."""
    reg = GainRegulator(0, 625)
    step = reg.consider(0.4, 0.0)
    assert step is not None and step.gain == GAIN_FLOOR and step.uncertain and 2.0 < step.factor < 2.5
    reg = GainRegulator(0, 625)
    assert reg.consider(0.8, 0.0) is None and reg.settled   # x2.2 would be farther from the empty house
    reg = GainRegulator(0, 625)
    step = reg.consider(1.6, 0.0)
    assert step is not None and step.exposure == EXPOSURES[1] and step.factor < 1.0


def test_an_exposure_the_full_setting_chose_outside_the_steps_is_left_to_it():
    reg = GainRegulator(GAIN_FLOOR, 39)
    assert reg.consider(1.5, 0.0) is None and reg.at_limit


@pytest.mark.parametrize("exposure", [39, 78, 156, 312, 625])
def test_no_values_of_the_webcam_break_the_regulator(exposure):
    """Whatever the full setting left (gain 0 in a bright hall, an exposure outside the steps): no error, and every
    step is expected to bring the light of the rooms closer to the empty house."""
    for gain in (0, 4, 8, 11, 12, 13, 32, 100, 254, 255):
        for ratio in (0.2, 0.5, 0.9, 1.0, 1.2, 2.0, 5.0):
            for cap in (CAP, CAP_ADAPT):
                reg = GainRegulator(gain, exposure)
                step = reg.consider(ratio, 0.0, cap)
                if step is not None:
                    assert abs(math.log(ratio * step.factor)) < abs(math.log(ratio)), (gain, exposure, ratio, step)
                    assert (step.factor > 1) == (ratio < 1), (gain, exposure, ratio, step)


def test_busy_until_the_light_is_back_or_nothing_more_can_be_done():
    reg = GainRegulator(32)
    assert not reg.busy
    step = reg.consider(0.7, 0.0)
    assert reg.busy                                          # waiting for the step to show
    reg.done(step, 0.2)
    assert reg.busy                                          # 0.7 was seen: more is coming
    reg.consider(1.0, 1.0)
    assert not reg.busy
    reg = GainRegulator(GAIN_MAX, 625)
    step = reg.consider(0.5, 0.0)
    assert step is not None and step.exposure in DIGITAL and step.gain == GAIN_MAX     # the digital light first
    reg = GainRegulator(GAIN_MAX, LADDER[0])
    reg.consider(0.5, 0.0)
    assert reg.at_limit and reg.at_dark_end and not reg.busy


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
