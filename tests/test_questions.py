# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Questions of the house answered aloud with no Talk button or from a phone, and every event told."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from domotiq.app import build, parse_args
from domotiq.voice import chatter as chatter_mod
from domotiq.voice import narrator as narrator_mod

KITCHEN, LIVING = (80, 100), (300, 100)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(chatter_mod, "ECHO_S", 0.0)
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.app import _wire
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    _wire(c)
    c.voice.listener = SimpleNamespace(ok=True)
    c.voice.mic.device = "test"
    c.said = []
    c.bus.subscribe("say", lambda ev: c.said.append(ev.get("text")))
    c.assigned = []
    c.vision.assign = lambda track, ident: c.assigned.append((track, ident))
    v = c.voice

    async def speak(*args, **kwargs):
        v.in_flight += 1
        await asyncio.sleep(0)
        v.in_flight -= 1
        v.voice_end = time.monotonic()
    v.speak = speak
    yield c
    c.store.close()


def hear(ctx, answers):
    queue = list(answers)
    last = {"text": ""}

    async def listen(grammar_words, *, stop=None, max_s=5.0, auto_end=True):
        item = queue.pop(0) if queue else ""
        if callable(item):
            item = await item(stop)
        last["text"] = item
        return item, 1.0 if item else 0.0, b"x" if item else b""

    async def recognize(audio, grammar_words):
        return last["text"], 1.0 if last["text"] else 0.0
    ctx.voice._listen, ctx.voice._recognize = listen, recognize


def newcomer(ctx, candidates=(), category="person", room="living"):
    ctx.bus.publish("vision_question", track={"id": "t-new", "identity": None, "room": room,
                                              "category": category, "color": "#c03030"},
                    candidates=list(candidates))


async def settle(ctx):
    await asyncio.sleep(0.05)
    for _ in range(50):
        if not ctx.voice._asking or ctx.voice._asking.done():
            break
        await asyncio.sleep(0.02)


def test_a_newcomer_is_asked_about_and_named_aloud_without_talk(ctx):
    async def scenario():
        hear(ctx, ["si chiama rosaria", "sì"])
        newcomer(ctx)
        await settle(ctx)
        assert ctx.said[0] == "C'è una persona nuova in soggiorno: come si chiama?"
        assert ctx.said[1] == "Si chiama Rosaria, giusto?"
        ident = ctx.identities.by_name("Rosaria")
        assert ident is not None and ident.category == "person" and ident.color == "#c03030"
        assert ctx.assigned == [("t-new", ident.id)]
        assert not ctx.house.confirmations                 # answered
    asyncio.run(scenario())


def test_a_newcomer_is_one_of_the_registered_characters(ctx):
    async def scenario():
        viola = ctx.identities.add("Viola", "person")
        braun = ctx.identities.add("Mister Braun", "person")
        hear(ctx, ["è viola"])
        newcomer(ctx, [viola.id, braun.id])
        await settle(ctx)
        assert ctx.said[0] == "C'è una persona nuova in soggiorno: chi è? Viola o Mister Braun?"
        assert ctx.assigned == [("t-new", viola.id)]
        assert ctx.said[-1] == "Grazie!"
    asyncio.run(scenario())


def test_the_first_answer_wins_a_phone_before_the_voice(ctx):
    async def scenario():
        viola = ctx.identities.add("Viola", "person")

        async def phone_answers(stop):
            cid = next(iter(ctx.house.confirmations))
            assert ctx.house.answer(cid, viola.id, by="web")
            await asyncio.wait_for(stop.wait(), 1.0)      # the house stops listening at once
            return ""
        hear(ctx, [phone_answers])
        newcomer(ctx, [viola.id])
        await settle(ctx)
        assert ctx.assigned == [("t-new", viola.id)]
        assert "Grazie!" not in ctx.said
        cid = "nothing"
        assert not ctx.house.answer(cid, "late", by="voice")
    asyncio.run(scenario())


def test_a_new_name_typed_on_a_phone(ctx):
    async def scenario():
        hear(ctx, [""] * 4)
        newcomer(ctx, category="dog", room="kitchen")
        await settle(ctx)
        assert ctx.said[0] == "C'è un cane nuovo in cucina: come si chiama?"
        cid, conf = next(iter(ctx.house.confirmations.items()))
        assert conf["allow_name"]
        assert ctx.house.answer(cid, {"name": "Fido"}, by="web")
        fido = ctx.identities.by_name("Fido")
        assert fido is not None and fido.category == "dog" and ctx.assigned == [("t-new", fido.id)]
    asyncio.run(scenario())


# ------------------------------------------------------------------ every event told
def ev(kind, **data):
    return SimpleNamespace(get=data.get, type=kind)


def test_moves_are_told_once_they_settle(ctx, monkeypatch):
    n = ctx.voice.narrator
    said = []
    monkeypatch.setattr(n, "_quiet", lambda: True)
    ctx.voice._spawn = lambda coro: (coro.close(), None)[1]
    t0 = time.monotonic()
    n._on_enter(ev("room_enter", track="a", name="Viola", category="person", room="living", other=None))
    assert n.tick(t0 + 0.5) == []                         # not yet: it may be passing by
    said += n.tick(t0 + narrator_mod.SETTLE_S + 0.1)
    assert said[-1]["it"] == "Ecco Viola in soggiorno!"
    # through the kitchen to the bedroom in a moment: only where it stops
    n._on_enter(ev("room_enter", track="a", name="Viola", category="person", room="kitchen", other="living"))
    n._on_enter(ev("room_enter", track="a", name="Viola", category="person", room="bedroom", other="kitchen"))
    said += n.tick(time.monotonic() + 10)
    assert said[-1] == {"it": "Viola va in camera.", "en": "Viola goes to the bedroom."}
    n._on_exit(ev("room_exit", track="a", name="Viola", category="person", room="bedroom", other=None))
    said += n.tick(time.monotonic() + 20)
    assert said[-1]["it"] == "Ciao Viola, a presto!"
    # a newcomer the house does not know is asked about, not announced
    n._on_enter(ev("room_enter", track="b", name="", category="person", room="living", other=None))
    assert n.tick(time.monotonic() + 30) == []
    # came and went before it settled: nothing
    n._on_enter(ev("room_enter", track="c", name="Rosaria", category="person", room="garden", other=None))
    n._on_exit(ev("room_exit", track="c", name="Rosaria", category="person", room="garden", other=None))
    assert n.tick(time.monotonic() + 40) == []
    # through the front door, and two at once in one go
    n._on_enter(ev("room_enter", track="d", name="Luca", category="person", room="living", other="driveway"))
    n._on_enter(ev("room_enter", track="e", name="Sara", category="person", room="kitchen", other="living"))
    lines = n.tick(time.monotonic() + 50)
    assert [x["it"] for x in lines] == ["Luca entra in casa.", "Sara va in cucina."]


def test_a_question_about_something_gone_is_withdrawn(ctx):
    async def scenario():
        hear(ctx, [""] * 4)
        newcomer(ctx)
        await asyncio.sleep(0.05)
        assert ctx.house.confirmations
        ctx.bus.publish("track_disappear", track="t-new", room="living")
        await settle(ctx)
        assert not ctx.house.confirmations and ctx.assigned == []
    asyncio.run(scenario())
