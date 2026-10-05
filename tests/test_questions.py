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
    from domotiq.voice import variants
    monkeypatch.setattr(variants.VARIETY, "pick", lambda key, options: options[0])   # the first way of saying it
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

    async def listen(grammar_words, *, stop=None, max_s=5.0, auto_end=True, **_):
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
        # what the house thinks it is, to be confirmed, and the name: never the registered persons
        assert ctx.said[0] == "In soggiorno vedo una persona nuova, giusto? Come si chiama?"
        assert ctx.said[1] == "Una persona di nome Rosaria, giusto?"
        assert ctx.said[2] == "Piacere, Rosaria!"
        ident = ctx.identities.by_name("Rosaria")
        assert ident is not None and ident.category == "person" and ident.color == "#c03030"
        assert ctx.assigned == [("t-new", ident.id)]
        assert not ctx.house.confirmations                 # answered
    asyncio.run(scenario())


def test_a_newcomer_is_one_of_the_registered_characters(ctx):
    async def scenario():
        viola = ctx.identities.add("Viola", "person")
        hear(ctx, ["è viola"])
        newcomer(ctx)                                     # a person: the name is asked, none proposed
        await settle(ctx)
        assert ctx.assigned == [("t-new", viola.id)]
        assert ctx.said[-1] == "Ah, è Viola! Grazie."
        # an animal: only the registered animals are proposed
        fido = ctx.identities.add("Fido", "dog")
        birba = ctx.identities.add("Birba", "cat")
        hear(ctx, ["fido"])
        ctx.bus.publish("vision_question", track={"id": "t-dog", "identity": None, "room": "garden",
                                                  "category": "dog", "color": "#806040"},
                        candidates=[fido.id, birba.id])
        await settle(ctx)
        assert ctx.said[-2] == "In giardino vedo un cane nuovo, giusto? È Fido o Birba, o come si chiama?"
        assert ctx.assigned[-1] == ("t-dog", fido.id)
    asyncio.run(scenario())


def test_both_of_them_when_two_figurines_touch(ctx):
    async def scenario():
        viola, rosaria = ctx.identities.add("Viola", "person"), ctx.identities.add("Rosaria", "person")
        together = []
        ctx.vision.together = lambda track, ids: together.append((track, list(ids)))
        # a newcomer: "sono Viola e Rosaria", the blob is the two of them
        hear(ctx, ["sono viola e rosaria"])
        newcomer(ctx)
        await settle(ctx)
        assert together == [("t-new", [viola.id, rosaria.id])]
        assert ctx.said[-1] == "Ah, sono in due: Viola e Rosaria!"
        # two look-alikes: "È Viola o Rosaria?" "Tutti e due!"
        hear(ctx, ["tutti e due"])
        ctx.bus.publish("vision_question", track={"id": "t-twin", "identity": viola.id, "room": "living",
                                                  "category": "person", "color": "#7030c0"},
                        candidates=[viola.id, rosaria.id])
        await settle(ctx)
        assert together[-1] == ("t-twin", [viola.id, rosaria.id])
        assert ctx.said[-1] == "Ah, sono in due: Viola e Rosaria!"
        assert not ctx.house.confirmations
    asyncio.run(scenario())


def test_a_denied_name_is_not_the_answer(ctx):
    async def scenario():
        viola, rosaria = ctx.identities.add("Viola", "person"), ctx.identities.add("Rosaria", "person")
        q = {"id": "q", "options": [{"value": viola.id, "label": {"it": "Viola", "en": "Viola"}},
                                    {"value": rosaria.id, "label": {"it": "Rosaria", "en": "Rosaria"}}]}
        answers = []
        ctx.house.answer = lambda cid, value, by="web": answers.append(value) or True
        assert await ctx.voice._answer_question("non è Viola, è Rosaria", q) and answers == [rosaria.id]
        for text in ("né Viola né Rosaria", "non è Viola", "non sono tutti e due", "non sono insieme"):
            assert not await ctx.voice._answer_question(text, q), text
        assert answers == [rosaria.id]
        assert await ctx.voice._answer_question("tutti e due", q) and answers[-1] == {"together": [viola.id, rosaria.id]}
    asyncio.run(scenario())


def test_both_but_one_is_seen_somewhere_else(ctx):
    async def scenario():
        from domotiq.model import Track
        viola, rosaria = ctx.identities.add("Viola", "person"), ctx.identities.add("Rosaria", "person")
        together = []
        ctx.vision.together = lambda track, ids: together.append((track, list(ids)))
        ctx.house.update_tracks([Track("t-v", *KITCHEN, category="person", identity=viola.id)])
        hear(ctx, ["sia viola che rosaria"])
        newcomer(ctx)
        await settle(ctx)
        # Viola is in the kitchen, in sight: here there is only Rosaria
        assert together == [] and ctx.assigned == [("t-new", rosaria.id)]
        assert ctx.said[-1] == "Ah, è Rosaria! Grazie."
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
        assert not any("Grazie" in x for x in ctx.said)
        cid = "nothing"
        assert not ctx.house.answer(cid, "late", by="voice")
    asyncio.run(scenario())


def test_a_new_name_typed_on_a_phone(ctx):
    async def scenario():
        hear(ctx, [""] * 4)
        newcomer(ctx, category="dog", room="kitchen")
        await settle(ctx)
        assert ctx.said[0] == "In cucina vedo un cane nuovo, giusto? Come si chiama?"
        cid, conf = next(iter(ctx.house.confirmations.items()))
        assert conf["allow_name"]
        # the phone corrects what it is too
        assert ctx.house.answer(cid, {"name": "Fido", "category": "cat"}, by="web")
        fido = ctx.identities.by_name("Fido")
        assert fido is not None and fido.category == "cat" and ctx.assigned == [("t-new", fido.id)]
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


# ------------------------------------------------------------------ any answer to "who is it?"
def test_nothing_there_makes_the_house_forget_it(ctx):
    async def scenario():
        dismissed = []
        ctx.vision.dismiss = dismissed.append
        hear(ctx, ["ma non c'è nessuno in giardino"])
        newcomer(ctx, room="garden")
        await settle(ctx)
        assert dismissed == ["t-new"] and not ctx.house.confirmations
        assert ctx.said[-1] == "Ah, allora ho visto male: scusate!"
        assert ctx.identities.all() == []
    asyncio.run(scenario())


def test_what_it_is_is_corrected_and_then_named(ctx):
    async def scenario():
        hear(ctx, ["no", "è un gatto", "micia", "sì"])
        newcomer(ctx)
        await settle(ctx)
        assert ctx.said[1:5] == ["Ah, scusa! Allora cos'è: una persona, un animale, un'auto o un oggetto?",
                                 "Ah, un gatto! Come si chiama?", "Si chiama Micia, giusto?", "Piacere, Micia!"]
        micia = ctx.identities.by_name("Micia")
        assert micia is not None and micia.category == "cat"
    asyncio.run(scenario())


def test_a_command_instead_of_a_name_is_answered_then_asked_again(ctx):
    async def scenario():
        hear(ctx, ["che ore sono", "marco", "no si chiama marta", "sì"])
        newcomer(ctx)
        await settle(ctx)
        i = ctx.said.index("E il nuovo arrivato in soggiorno? Come si chiama?")
        assert i >= 2                                      # the time (or that it is unknown) was said first
        assert ctx.said[i + 1:] == ["Una persona di nome Marco, giusto?", "Una persona di nome Marta, giusto?",
                                    "Piacere, Marta!"]
        assert ctx.identities.by_name("Marta") and not ctx.identities.by_name("Marco")
    asyncio.run(scenario())


def test_not_knowing_leaves_the_question_to_the_phones(ctx):
    async def scenario():
        hear(ctx, ["boh, non lo so"])
        newcomer(ctx)
        await settle(ctx)
        assert ctx.said[-1] == "Va bene, nessun problema: se vuoi me lo dici dalla webapp."
        assert ctx.house.confirmations                     # still on the phones
    asyncio.run(scenario())


def test_a_long_answer_is_understood_by_the_language_model(ctx):
    from domotiq.voice import who

    class Model:
        sentences = []

        async def classify(self, sentence, names):
            self.sentences.append(sentence)
            return who.parse("kind cat Romeo", sentence, names, 0.9)
    async def scenario():
        ctx.voice.llm = Model()
        hear(ctx, ["allora praticamente quello che vedi è il gatto del vicino che si chiama romeo", "esatto"])
        newcomer(ctx)
        await settle(ctx)
        assert Model.sentences and ctx.said[1] == "Si chiama Romeo, giusto?"
        romeo = ctx.identities.by_name("Romeo")
        assert romeo is not None and romeo.category == "cat"
    asyncio.run(scenario())


# ------------------------------------------------------------------ the buttons and the voice
def test_the_buttons_light_up_while_listening_and_breathe_while_thinking(ctx, monkeypatch):
    from domotiq import activities
    monkeypatch.setattr(activities, "BREATH_STEP_S", 0.01)
    sent = []

    async def leds(mask, blink=0):
        sent.append((mask, blink))
    ctx.mcu.leds = leds
    a = ctx.actions

    async def scenario():
        await a.update_leds(listening=True)
        assert sent[-1] == (7, 0)                           # all three while the house listens
        await a.thinking(True)
        await asyncio.sleep(0.08)
        breath = [m for m, _ in sent[1:]]
        assert set(breath) <= {0b010, 0b111, 0b000} and {0b010, 0b111} <= set(breath)
        await a.thinking(False)                             # it speaks: back to the language LED
        assert sent[-1] == (0, 0)
        n = len(sent)
        await asyncio.sleep(0.05)
        assert len(sent) == n                               # and the breath has stopped
    asyncio.run(scenario())


def test_come_si_chiama_is_said_with_every_vowel():
    from domotiq.voice import tts
    assert tts.normalize("Ah, un gatto! Come si chiama?", "it") == "Ah, un gatto! [[ kˈome si kjˈaːma? ]]"
    assert tts.normalize("E il nuovo arrivato: come si chiama?", "it").endswith("[[ kˈome si kjˈaːma? ]]")
    assert tts.normalize("What's the name?", "en") == "What's the name?"


def test_a_name_already_in_the_house_means_the_newcomer_was_nothing(ctx):
    from domotiq.model import Track

    async def scenario():
        dismissed = []
        ctx.vision.dismiss = dismissed.append
        viola = ctx.identities.add("Viola", "person")
        ctx.house.tracks["t-viola"] = Track("t-viola", 300, 100, "person", viola.id, "living")
        hear(ctx, ["è viola"])
        newcomer(ctx, room="bathroom")
        await settle(ctx)
        assert dismissed == ["t-new"] and ctx.assigned == []
        assert ctx.said[-1] == "Viola è già in soggiorno: allora qui ho visto male, scusate!"
        # hidden for a moment there, she may well be the newcomer: then the name moves
        ctx.house.tracks["t-viola"].hidden = True
        hear(ctx, ["è viola"])
        newcomer(ctx, room="bathroom")
        await settle(ctx)
        assert ctx.assigned == [("t-new", viola.id)]
    asyncio.run(scenario())


def test_the_house_asks_the_time_and_hears_it_with_no_talk(ctx):
    async def scenario():
        ctx.clock.source = "unknown"                     # the board started with no network and no phone yet
        hear(ctx, ["sono le tre e mezza"])
        await ctx.voice.ask_time()
        assert ctx.said[0] == "Non so che ore sono: che ore sono adesso?"
        assert ctx.said[-1] == "Grazie! Allora sono le 3 e 30."
        assert ctx.clock.known
    asyncio.run(scenario())


def test_the_house_says_things_in_different_ways():
    from domotiq.voice import variants
    v = variants.Variety(seed=1)
    said = [v.pick("k", variants.LEAVE) for _ in range(30)]
    assert all(a != b for a, b in zip(said, said[1:]))       # never twice in a row
    assert len(set(said)) == len(variants.LEAVE)              # and every way is used
    # a name typed by a visitor is put in place, never read as a format
    assert variants.fill(("Ciao {name}!", "Hi {name}!"), name="{name:>9}") == ("Ciao {name:>9}!", "Hi {name:>9}!")


def test_on_the_bed_it_is_said_and_off_the_table_it_is_asked(ctx, monkeypatch):
    from domotiq.model import Track
    n = ctx.voice.narrator
    monkeypatch.setattr(n, "_quiet", lambda: True)
    ctx.voice._spawn = lambda coro: (coro.close(), None)[1]
    viola = ctx.identities.add("Viola", "person")
    ctx.house.tracks["t-v"] = Track("t-v", 527, 170, "person", viola.id, "bedroom", on="bed")
    n._on_enter(ev("room_enter", track="t-v", name="Viola", category="person", room="bedroom", other="living"))
    lines = n.tick(time.monotonic() + 5)
    assert lines[-1]["it"] == "Viola è sul letto della camera."
    ctx.house.tracks["t-v"].on = "kitchen-table"
    n._on_furniture(ev("furniture", track="t-v", name="Viola", category="person", room="kitchen",
                       on="kitchen-table", before=None))
    lines = n.tick(time.monotonic() + 10)
    assert lines[-1]["it"] == "Viola, scendi subito dal tavolo!"
    from domotiq.voice import answers
    assert answers.where_is(ctx, "Viola", "it") == "Viola è sul tavolo della cucina."
