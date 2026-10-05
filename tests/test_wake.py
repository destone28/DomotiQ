# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The word of activation in place of Talk, and the LEDs of the buttons: steady while the house speaks, blinking
while it listens."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from domotiq.voice.intents import spoken
from test_offers import KITCHEN, ctx, place, script  # noqa: F401 - the fixture


def test_numbers_in_the_word_are_said_in_words():
    assert spoken("Casa 2", "it") == spoken("casa2", "it") == spoken("casa due", "it") == "casa due"
    assert spoken("Casa 21", "it") == "casa ventuno" and spoken("Casa 28", "it") == "casa ventotto"
    assert spoken("House 21", "en") == "house twenty one" and spoken("R2D2", "en") == "r two d two"
    assert spoken("Ehi, Casa!", "it") == "ehi casa"


def test_the_word_of_activation_is_on_only_when_chosen(ctx):
    v = ctx.voice
    assert v.wake_phrase() == ""
    ctx.settings.set("voice.wake_enabled", True)
    ctx.settings.set("voice.wake_word", "Casa 1")
    assert v.wake_phrase() == "casa uno"
    v.listener = SimpleNamespace(ok=True, known=lambda w, lang: w != "zork")
    assert v.wake_check("Zork 2") == {"spoken": "zork due", "unknown": ["zork"]}


def test_the_word_waits_for_the_house_to_be_free(ctx):
    async def scenario():
        v = ctx.voice
        assert v._wake_free()
        v.in_flight = 1                                        # the house speaks: its own voice may say the word
        assert not v._wake_free()
        v.in_flight = 0
        async with v.busy:                                     # a conversation, a question of the house
            assert not v._wake_free()
        ctx.settings.set("voice.verbosity", "silent")          # it could not answer
        assert not v._wake_free()
    asyncio.run(scenario())


def test_the_word_does_what_talk_does(ctx):
    async def scenario():
        v = ctx.voice
        place(ctx, "Marco", KITCHEN)
        handled = []

        async def handle(text):
            handled.append(text)
        v.handle = handle
        await v._woken("che ore sono")                         # "Casa, che ore sono?": all at once
        assert handled == ["che ore sono"] and not ctx.said
        script(ctx, ["accendi la luce in cucina"])
        await v._woken("")                                     # "Casa": the house asks, then listens
        assert ctx.said[-1] == "Dimmi, di cosa hai bisogno?" and handled[-1] == "accendi la luce in cucina"
    asyncio.run(scenario())


def test_the_leds_steady_while_speaking_blinking_while_listening(ctx):
    async def scenario():
        sent = []

        async def leds(mask, blink=0):
            sent.append((mask, blink))
        ctx.mcu.leds = leds
        act = ctx.actions
        await act.update_leds(listening=True)
        assert sent[-1] == (7, 7)
        await act.speaking(True)                               # it speaks while the microphone is already open
        assert sent[-1] == (7, 0)
        await act.speaking(False)
        assert sent[-1] == (7, 7)                              # still listening
        await act.update_leds()
        assert sent[-1] == (0, 0)
    asyncio.run(scenario())
