# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house does with what it heard at the bench (casa1, 5 and 6 October): the air conditioning asked
aloud, a fact told as it is, the narrator at the edge of the picture, its own voice while it listens, newcomers
nobody answers about, talk nearby taken for an answer, the summary of a full house."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from domotiq.model import Track
from domotiq.voice import facts, who
from domotiq.voice import manager as manager_mod
from domotiq.voice.intents import Intent, parse
from test_offers import KITCHEN, ctx, place  # noqa: F401 - the fixture

NAMES = ["Mister Brown", "Viola", "Rossana", "Honda Civic", "Mister Green", "Mister Blu", "Rossellina", "Giallo Galli"]


def ev(kind, **data):
    return SimpleNamespace(get=data.get, type=kind)


# ------------------------------------------------------------------ the air conditioning and the heating
@pytest.mark.parametrize("text,mode,on", [
    ("accendi condizionatore", "cool", True), ("condizionatore", "cool", True),
    ("accendi il climatizzatore", "cool", True), ("spegni il climatizzatore", "cool", False),
    ("accendi il riscaldamento", "warm", True), ("accendi il clima", "cool", True),
    ("turn on the air conditioning", "cool", True), ("turn off the heating", "warm", False),
])
def test_the_air_conditioning_and_the_heating_are_no_lights(text, mode, on):
    i = parse(text, NAMES)
    assert i.name == "climate" and i.args == {"mode": mode, "on": on}


def test_the_air_conditioning_is_a_wave_of_light_in_every_room(ctx):
    async def scenario():
        await ctx.voice.execute(parse("accendi il condizionatore", []))
        assert ctx.said[-1] == "Accendo il climatizzatore."
        assert all(stack["climate"].effect == "cool" for stack in ctx.lights.layers.values())
        await ctx.voice.execute(parse("spegni il condizionatore", []))
        assert ctx.said[-1] == "Climatizzatore spento."
        assert not any("climate" in stack for stack in ctx.lights.layers.values())
        await ctx.voice.execute(parse("accendi il riscaldamento", []))
        assert ctx.said[-1] == "Accendo il riscaldamento."
        assert all(stack["climate"].effect == "warm" for stack in ctx.lights.layers.values())
    asyncio.run(scenario())


# ------------------------------------------------------------------ a fact told as it is
def test_a_fact_told_as_it_is_is_learned(ctx):
    """"Il colore preferito di Mister Blu è l'azzurro" was answered "di Mister Blu questo non lo so ancora"."""
    async def scenario():
        blu = ctx.identities.add("Mister Blu", "person")
        ctx.identities.update(blu.id, facts=["ha come colore preferito il rosso"])      # an older answer
        await ctx.voice.handle("il colore preferito di mister blu è l'azzurro")
        assert ctx.said[-1] == "Me lo ricorderò: Mister Blu ha come colore preferito l'azzurro."
        assert ctx.identities.get(blu.id).facts == ["ha come colore preferito l'azzurro"]
        assert facts.favourite_colour(ctx.identities.get(blu.id).facts) == "cyan"
        green = ctx.identities.add("Mister Green", "person")
        await ctx.voice.handle("il lavoro di mister green è il pompiere")
        assert ctx.identities.get(green.id).facts == ["fa il pompiere"]
    asyncio.run(scenario())


def test_questions_stay_questions():
    assert parse("qual è il colore preferito di mister blu", NAMES).name == "ask_fact"
    assert parse("il colore preferito di mister blu è il rosso?", NAMES).name == "ask_fact"
    assert parse("il colore preferito di viola e rossana", NAMES).name != "fact"     # two characters
    assert parse("la casa di viola è in cucina", NAMES) is None or parse("la casa di viola è in cucina",
                                                                          NAMES).name != "fact"


def test_a_restaurant_is_about_food_and_a_name_heard_by_one_word_is_no_colour():
    assert facts.question_topic("se devo andare al ristorante con rossellina", NAMES) == "food"
    assert facts.question_topic("le misure brown", NAMES) is None                # "brown" was taken for a colour
    assert facts.question_topic("che lavoro fa james brown", NAMES) == "job"


# ------------------------------------------------------------------ the narrator at the edge of the picture
def test_a_character_coming_and_going_is_not_told_every_minute(ctx, monkeypatch):
    """"Mister Brown, scendi dalla fioriera" and "a presto Mister Brown" were said every minute."""
    n = ctx.voice.narrator
    monkeypatch.setattr(n, "_quiet", lambda: True)
    ctx.voice._spawn = lambda coro: (coro.close(), None)[1]
    brown = ctx.identities.add("Mister Brown", "person")
    t0 = time.monotonic()
    said = []
    for k in range(4):                    # on the table, out of sight, on the table again: every minute
        now = t0 + 60 * k
        ctx.house.tracks["t-b"] = Track("t-b", 80, 100, "person", brown.id, "kitchen", on="kitchen-table")
        n._on_enter(ev("room_enter", track="t-b", name="Mister Brown", category="person", room="kitchen",
                       other=None))
        said += n.tick(now + 5)
        del ctx.house.tracks["t-b"]
        n._on_exit(ev("room_exit", track="t-b", name="Mister Brown", category="person", room="kitchen",
                      other=None, identity=brown.id))
        said += n.tick(now + 30)
    assert len(said) == 2 and "tavolo" in said[0]["it"] and "Mister Brown" in said[1]["it"]
    # a move from one room to another is always news
    ctx.house.tracks["t-b"] = Track("t-b", 300, 100, "person", brown.id, "living")
    n._on_enter(ev("room_enter", track="t-b", name="Mister Brown", category="person", room="living",
                   other="kitchen"))
    assert "soggiorno" in n.tick(t0 + 300)[-1]["it"]


# ------------------------------------------------------------------ its own voice while it listens
def test_the_house_does_not_take_its_own_voice_for_an_answer(ctx, monkeypatch):
    """The narrator spoke while the house waited for an answer: "per favore" was heard from its own line."""
    monkeypatch.setattr(manager_mod, "SELF_ECHO_S", 0.0)
    v = ctx.voice
    fed = []

    class Session:
        def feed(self, chunk):
            fed.append(chunk[0])

        def result(self):
            return "", 0.0
    v.listener = SimpleNamespace(ok=True, session=lambda lang, grammar, *rest: Session())
    out = SimpleNamespace(speaking=False)
    ctx.audio = out

    class Mic:
        available, last_level = True, 0.0

        async def listen(self, stop, on_chunk, max_s=60.0, min_s=0.0):
            for i in range(12):
                out.speaking = 4 <= i < 8                 # a line of the narrator plays in the middle
                on_chunk(bytes([i]) * 4)
                await asyncio.sleep(0.01)
            return b""
    v.mic = Mic()
    asyncio.run(v._listen(None, max_s=5.0, auto_end=False))
    assert fed == [0, 1, 2, 3, 8, 9, 10, 11]


def test_a_question_waits_for_a_line_already_on_its_way(ctx):
    async def scenario():
        v = ctx.voice
        out = SimpleNamespace(speaking=True)
        ctx.audio = out

        async def ends():
            await asyncio.sleep(0.3)
            out.speaking = False
        asyncio.ensure_future(ends())
        t = time.monotonic()
        await v._silent()
        assert time.monotonic() - t >= 0.25
    asyncio.run(scenario())


# ------------------------------------------------------------------ newcomers nobody answers about
def test_newcomers_nobody_answers_about_are_asked_on_the_phones_for_a_while(ctx, monkeypatch):
    async def scenario():
        v = ctx.voice
        runs = []

        async def run(ev, stop):
            runs.append(ev["id"])
            v.who.heard = False                    # nobody said anything
        monkeypatch.setattr(v.who, "run", run)
        for k in range(3):
            cid = f"q{k}"
            ctx.house.confirmations[cid] = {"id": cid}
            await v._ask_aloud({"id": cid, "question": {"it": f"Domanda {k}", "en": f"Question {k}"},
                                "context": {"kind": "who"}, "allow_name": True})
        assert runs == ["q0", "q1"] and "Domanda 2" not in ctx.said
        v._who_quiet_until = 0.0                   # a while later it asks aloud again
        ctx.house.confirmations["q3"] = {"id": "q3"}
        await v._ask_aloud({"id": "q3", "question": {"it": "Domanda 3", "en": "Question 3"},
                            "context": {"kind": "who"}, "allow_name": True})
        assert runs[-1] == "q3"
    asyncio.run(scenario())


def test_talk_nearby_is_no_answer_to_who_is_it():
    """"Si sta allenando per migliorare la velocità del modello" was taken for "it's a car"."""
    assert who.parse("kind car", "si sta allenando per migliorare la velocità del modello", [], 0.54).kind == "other"
    assert who.parse("kind car", "è una macchina", [], 0.9).kind == "kind"


# ------------------------------------------------------------------ the summary of a full house
def test_the_summary_tells_every_person(ctx):
    for name in ("Anna", "Bruno", "Carla", "Dario", "Elena", "Franco", "Gina"):
        place(ctx, name, KITCHEN)
    from domotiq.voice import answers
    line = answers.summary(ctx, "it")
    assert line.startswith("In casa ci sono 7 persone:") and "altre 2 persone" in line


# ------------------------------------------------------------------ one word the rules do not understand
def test_one_word_nobody_understands_is_not_answered_with_a_story(ctx):
    """"Domani" got "Io so tutto di questa casa, ma del resto del mondo proprio niente"."""
    async def scenario():
        v = ctx.voice

        async def understand(text, names):
            return Intent("other", {}, 0.52, "llm")
        v.llm = SimpleNamespace(understand=understand, remembers=lambda text, names: True)
        await v.handle("domani")
        assert "capito" in ctx.said[-1]
    asyncio.run(scenario())
