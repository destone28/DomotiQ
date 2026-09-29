# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Registering characters from the intercom and with the Talk button, on a simulated house."""

from __future__ import annotations

import asyncio
import time

import pytest

from domotiq.app import build, parse_args


@pytest.fixture
def ctx(tmp_path):
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    c.voice.say = _silent               # no speech synthesis in the tests
    c.voice.reply = _silent2
    yield c
    c.store.close()


async def _silent(*args, **kwargs):
    return None


async def _silent2(*args, **kwargs):
    return None


def _step(ctx, now):
    ctx.house.update_tracks(ctx.sim.tracks(), now)
    ctx.registration.poll()


def test_intercom_registers_the_first_stranger_through_the_door(ctx):
    async def scenario():
        await ctx.voice._register_named("Leo", "intercom")
        assert ctx.voice.expect_entrance and ctx.voice.expect_entrance["new"] == "Leo"
        # someone already inside is not taken: only who comes in from the driveway
        ctx.sim.add(300, 150, "person", None, "#20a0e0", "")
        obj = ctx.sim.add(197, -30, "person", None, "#e0a020", "")
        now = time.time()
        _step(ctx, now)
        for y in (-10, 5, 20, 40):
            ctx.sim.move(obj.id, 197, y)
            now += 0.5
            _step(ctx, now)
        leo = ctx.identities.by_name("Leo")
        assert leo is not None
        assert ctx.house.tracks[obj.id].identity == leo.id
        assert ctx.voice.expect_entrance is None
        others = [t for t in ctx.house.tracks.values() if t.id != obj.id]
        assert all(t.identity is None for t in others)

    asyncio.run(scenario())


def test_talk_takes_the_only_newcomer_in_the_room(ctx):
    async def scenario():
        obj = ctx.sim.add(80, 100, "person", None, "#20a0e0", "")
        _step(ctx, time.time())
        await ctx.voice._register_named("Sofia", "voice", room="kitchen")
        sofia = ctx.identities.by_name("Sofia")
        assert sofia is not None and ctx.house.tracks[obj.id].identity == sofia.id

    asyncio.run(scenario())


def test_talk_waits_then_asks_the_web_app_to_choose(ctx):
    async def scenario():
        await ctx.voice._register_named("Ada", "voice", room="bedroom")
        (session,) = ctx.registration.sessions.values()
        assert session.status == "waiting" and session.auto
        a = ctx.sim.add(500, 100, "person", None, "#20a0e0", "")
        b = ctx.sim.add(560, 150, "person", None, "#a020e0", "")
        _step(ctx, time.time())
        assert session.status == "choose" and set(session.candidates) == {a.id, b.id}
        ctx.registration.pick(session.id, b.id)
        ada = ctx.identities.by_name("Ada")
        assert ada is not None and ctx.house.tracks[b.id].identity == ada.id

    asyncio.run(scenario())


def test_known_name_at_the_intercom(ctx):
    async def scenario():
        marco = ctx.identities.add("Marco", "person")
        ctx.voice.expect_entrance = {"identity": marco.id, "name": "Marco", "until": time.time() + 60}
        obj = ctx.sim.add(197, -30, "person", None, "#e0a020", "")
        now = time.time()
        _step(ctx, now)
        for y in (5, 20, 40):
            ctx.sim.move(obj.id, 197, y)
            now += 0.5
            _step(ctx, now)
        assert ctx.house.tracks[obj.id].identity == marco.id

    asyncio.run(scenario())
