# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
""""Fai domande" from the web app, and what the house does with the answers: the favourite colour, a party for
who loves dancing, the barbecue for who loves it."""

from __future__ import annotations

import asyncio
import time

from domotiq.voice import facts
from domotiq.voice.chatter import QUESTIONS
from test_offers import GARDEN, KITCHEN, LIVING, ctx, place, script  # noqa: F401 - the fixture

BEDROOM = (527, 170)


async def _until_free(ctx):
    for _ in range(100):
        if not ctx.voice.chatter.asking:
            return
        await asyncio.sleep(0.01)


def test_ask_questions_to_a_character_picked_or_at_random(ctx):
    async def scenario():
        ctx.settings.set("voice.verbosity", "normal")             # not only in chatty mode
        marco = place(ctx, "Marco", KITCHEN)
        ctx.identities.update(marco.id, facts=["ama ballare"])
        script(ctx, ["il blu"])
        result = ctx.voice.chatter.ask_now(None)
        assert result["ok"] and result["name"] == "Marco" and result["present"]
        await _until_free(ctx)
        # what it did not know yet: never "do you like dancing?" again before the rest
        assert not any("ballare" in s for s in ctx.said)
        # to a character not in the house, asked by name
        anna = ctx.identities.add("Anna", "person")
        script(ctx, ["la pizza"])
        result = ctx.voice.chatter.ask_now(anna.id)
        assert result["ok"] and result["name"] == "Anna" and not result["present"]
        await _until_free(ctx)
        assert any(s.startswith("Anna,") for s in ctx.said)
    asyncio.run(scenario())


def test_ask_questions_says_why_not(ctx):
    async def scenario():
        assert ctx.voice.chatter.ask_now(None) == {"ok": False, "error": "nobody"}
        ctx.settings.set("voice.verbosity", "silent")
        assert ctx.voice.chatter.ask_now(None)["error"] == "silent"
    asyncio.run(scenario())


def test_dance_and_barbecue_answers_become_facts(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        script(ctx, ["sì"])
        q = next(q for q in QUESTIONS if q["id"] == "a-dance")
        await ctx.voice.chatter._ask(marco.id, q, forced=True)
        assert facts.told(ctx.identities.get(marco.id).facts, "a-dance") == "yes"
    asyncio.run(scenario())


def test_who_loves_dancing_is_offered_a_party_in_the_living_room(ctx):
    async def scenario():
        marco = place(ctx, "Marco", LIVING)
        ctx.identities.update(marco.id, facts=["ama ballare"])
        chatter = ctx.voice.chatter
        assert chatter._pick() is None or chatter._pick()[1]["id"] != "f-party"     # alone: no party
        place(ctx, "Anna", LIVING)
        chatter._fan_at.clear()
        identity, q = chatter._pick()
        assert identity == marco.id and q["id"] == "f-party"
        assert chatter._pick()[1]["id"] != "f-party"            # not again for a while
        script(ctx, ["sì"])
        await chatter._ask(identity, q)
        assert ctx.done == ["party"]
        # who loves barbecues, in the garden
        tom = place(ctx, "Tom", GARDEN)
        ctx.identities.update(tom.id, facts=["adora le grigliate"])
        identity, q = chatter._pick()
        assert identity == tom.id and q["id"] == "f-grill"
    asyncio.run(scenario())


def test_the_favourite_light_of_a_character(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        lit = []

        async def light(room, color="#ffffff", effect="solid", brightness=60, duration_s=120):
            lit.append((room, color))
        ctx.actions.light = light
        # not told yet: the house asks, and the answer lights the room
        script(ctx, ["il verde"])
        await ctx.voice.handle("accendi la luce preferita di Marco")
        await _until_free(ctx)
        assert facts.favourite_colour(ctx.identities.get(marco.id).facts) == "green"
        assert lit[-1][1] in ("green", "#20e040")
        # now it knows: the room said, or the one Marco is in
        await ctx.voice.handle("accendi la luce preferita di Marco in camera")
        assert lit[-1] == ("bedroom", "green")
        await ctx.voice.handle("accendi la luce preferita di Marco")
        assert lit[-1] == ("kitchen", "green")
    asyncio.run(scenario())


def test_the_light_of_a_room_takes_the_favourite_colour_of_who_is_in(ctx):
    marco = place(ctx, "Marco", BEDROOM)
    ctx.identities.update(marco.id, facts=["ha come colore preferito il viola"])
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    lid = next(lid for lid, light in ctx.layout.lights.items() if light.room == "bedroom")
    assert ctx.house.lights.layers[lid]["follow"].color == "#a030ff"
    ctx.settings.set("lights", {**ctx.settings.get("lights"), "follow_favourite": False})
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    assert ctx.house.lights.layers[lid]["follow"].color == ctx.settings.get("lights")["follow_color"]
