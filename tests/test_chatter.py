# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Small talk without the Talk button: the welcome of a new phone and the questions of chatty mode."""

from __future__ import annotations

import asyncio
import random
import time
from types import SimpleNamespace

import pytest

from domotiq.app import build, parse_args
from domotiq.bus import Event
from domotiq.voice import chatter as chatter_mod
from domotiq.voice.chatter import QUESTIONS, grammar, react, yes_or_no

KITCHEN, LIVING, BATHROOM, GARDEN = (80, 100), (300, 100), (230, 300), (80, 300)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(chatter_mod, "GROUP_S", 0.0)
    monkeypatch.setattr(chatter_mod, "ECHO_S", 0.0)
    monkeypatch.setattr(chatter_mod, "GREET_GAP_S", 0.0)
    monkeypatch.setattr(chatter_mod, "THANK_GROUP_S", 0.0)
    monkeypatch.setattr(chatter_mod, "GENERATED_SHARE", 0.0)   # the questions of the list (stories: test_stories)
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    c.voice.listener = SimpleNamespace(ok=True)      # as if the speech model and the microphone were there
    c.voice.mic.device = "test"
    c.said = []
    c.bus.subscribe("say", lambda ev: c.said.append((ev.get("text"), ev.get("spoken"))))
    c.sent = []
    c.bus.subscribe("welcome", lambda ev: c.sent.append(dict(ev.data)))
    v = c.voice

    async def speak(*args, **kwargs):               # like the real one, without Piper
        v.in_flight += 1
        await asyncio.sleep(0)
        v.in_flight -= 1
        v.voice_end = time.monotonic()
    v.speak = speak
    yield c
    c.store.close()


def script(ctx, answers, free=None):
    """The microphone hears these answers, one per listen (a callable gets the stop event).

    The free recognition of the same audio says the same, unless `free` gives what it says instead.
    """
    queue = list(answers)
    last = {"text": ""}

    async def listen(grammar_words, *, stop=None, max_s=5.0, auto_end=True, **_):
        item = queue.pop(0) if queue else ""
        if callable(item):
            item = await item(stop)
        last["text"] = item
        return item, 1.0 if item else 0.0, b"x" if item else b""

    async def recognize(audio, grammar_words):
        text = last["text"] if free is None else free
        return text, 1.0 if text else 0.0
    ctx.voice._listen = listen
    ctx.voice._recognize = recognize


def place(ctx, name, where, category="person"):
    ident = ctx.identities.add(name, category)
    ctx.sim.add(*where, category, ident.id, "#e03030", name)
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    return ident


def question(qid):
    return next(q for q in QUESTIONS if q["id"] == qid)


def texts(ctx):
    return [t for t, _ in ctx.said]


INVITE_IT = chatter_mod.INVITE["it"]


# ------------------------------------------------------------------ answers
def test_yes_no_and_reactions():
    assert yes_or_no("sì certo", "it") is True
    assert yes_or_no("no grazie", "it") is False
    assert yes_or_no("perché no", "it") is True
    assert yes_or_no("non lo so", "it") is None
    assert yes_or_no("why not", "en") is True
    assert yes_or_no("dai andiamo", "it") is None                     # in a chat "dai" is not a yes (offers: test_offers)
    assert yes_or_no("si vede bene da qui", "it", strict=True) is None  # a pronoun in free speech
    assert yes_or_no("sì", "it", strict=True) is True
    rng = random.Random(1)
    reply, action, outcome = react(question("k-hungry"), "sì", "it", rng)
    assert action is None and reply["it"].startswith("Allora apri il frigo") and outcome == "yes"
    assert react(question("k-hungry"), "no", "it", rng)[2] == "no"
    reply, action, outcome = react(question("k-cook"), "la pizza", "it", rng)
    assert "Pizza" in reply["it"] and action is None and outcome == "option 0"
    assert react(question("k-cook"), "il sushi", "it", rng)[0] is chatter_mod.UNCLEAR
    assert react(question("a-colour"), "il blu", "it", rng)[1] == {"do": "light", "color": "blue", "brightness": 60}
    assert react(question("a-from"), "da Torino", "it", rng)[0] in chatter_mod.OPEN_REPLIES
    assert react(question("k-hungry"), "", "it", rng)[0] is chatter_mod.NO_ANSWER
    # a chat answer is never run as a command: "mi piace la musica" is not a yes to "hai fame?"
    assert react(question("k-hungry"), "mi piace la musica", "it", rng)[:2] == (chatter_mod.UNCLEAR, None)
    assert "pizza" in grammar(question("k-cook"), "it") and grammar(question("a-from"), "it") is None
    words = grammar(question("k-hungry"), "it")
    assert "perché no" in words and "non lo so" in words     # whole phrases, or the grammar would only hear "no"


def test_a_denied_choice_or_colour_is_not_the_answer():
    rng = random.Random(1)
    assert react(question("k-cook"), "non la pizza, la pasta", "it", rng)[2] == "option 1"
    assert react(question("k-cook"), "no, la pasta", "it", rng)[2] == "option 1"
    assert react(question("k-cook"), "pizza, not pasta", "en", rng)[2] == "option 0"
    assert react(question("g-trip"), "il mare no, la montagna", "it", rng)[2] == "option 1"
    assert react(question("k-cook"), "né la pizza né la pasta", "it", rng)[2] == "unclear"
    assert react(question("a-colour"), "non mi piace il rosso", "it", rng)[:3] == (chatter_mod.UNCLEAR, None, "unclear")
    assert react(question("a-colour"), "non so, il rosso", "it", rng)[2] == "colour red"
    assert react(question("a-colour"), "I don't like red, blue", "en", rng)[2] == "colour blue"


def test_every_question_has_both_languages():
    for q in QUESTIONS:
        assert q["text"]["it"] and q["text"]["en"], q["id"]
        for key in ("yes", "no", "reply"):
            if key in q:
                assert q[key]["it"] and q[key]["en"], (q["id"], key)
        for o in q.get("options", []):
            assert o["words"]["it"] and o["words"]["en"] and o["reply"]["it"] and o["reply"]["en"], q["id"]


# ------------------------------------------------------------------ questions
def test_a_chatty_question_is_answered_without_talk(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        script(ctx, ["pizza"])
        await ctx.voice.chatter._ask(marco.id, question("k-cook"))
        assert texts(ctx) == ["Marco, cosa cuciniamo stasera: pizza o pasta?", "Pizza! Accendo il forno, Marco."]
        ev = ctx.store.events(types=["chatter"])[0]["data"]
        assert ev["question"] == "k-cook" and ev["outcome"] == "option 0"
        assert "heard" not in ev and "pizza" not in str(ev)        # what the microphone heard is not kept
    asyncio.run(scenario())


def test_an_offer_is_carried_out_only_after_a_yes(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        ctx.settings.set("voice.verbosity", "chatty")
        done = []

        async def party():
            done.append("party")
            return True
        ctx.actions.party = party
        script(ctx, ["no"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert done == []
        script(ctx, ["sì volentieri"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert done == ["party"]
    asyncio.run(scenario())


def test_offers_that_cannot_run_are_not_made(ctx):
    place(ctx, "Tom", GARDEN)
    ch = ctx.voice.chatter
    track = next(iter(ch._present().values()))
    assert "o-grill" in [q["id"] for q in ch._questions_for(track)]
    ctx.house.grill_on = True
    assert "o-grill" not in [q["id"] for q in ch._questions_for(track)]


def test_the_colour_answer_lights_the_room_of_the_character(ctx):
    async def scenario():
        luca = place(ctx, "Luca", LIVING)
        ctx.settings.set("voice.verbosity", "chatty")
        script(ctx, ["il viola"])
        await ctx.voice.chatter._ask(luca.id, question("a-colour"))
        assert ctx.lights.state()["living"]["color"] == "purple"
    asyncio.run(scenario())


def test_a_word_the_grammar_made_out_of_noise_is_not_an_answer(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        script(ctx, ["mai"], free="")                  # the list heard "mai", the free recognition nothing
        await ctx.voice.chatter._ask(marco.id, question("a-house"))
        assert texts(ctx)[-1] == "Niente? Sarà per la prossima volta, Marco."
        assert ctx.store.events(types=["chatter"])[0]["data"]["outcome"] == "none"
    asyncio.run(scenario())


def test_an_answer_the_house_spoke_over_is_thrown_away(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")

        async def rule_speaks(stop):
            await ctx.actions.say({"it": "Attenzione: il locale tecnico è riservato!", "en": "x"})
            return "pizza"
        script(ctx, [rule_speaks])
        await ctx.voice.chatter._ask(marco.id, question("k-cook"))
        assert not any("Pizza!" in t for t in texts(ctx))
    asyncio.run(scenario())


def test_questions_come_only_in_chatty_mode_and_never_in_the_bathroom(ctx):
    async def scenario():
        ch = ctx.voice.chatter
        place(ctx, "Sara", BATHROOM)
        ctx.settings.set("voice.verbosity", "normal")
        ch.tick(1000.0)
        assert ch.next_at is None
        ctx.settings.set("voice.verbosity", "chatty")
        ch.tick(1000.0)
        assert ch.next_at is not None and ch.next_at >= 1000.0 + chatter_mod.MIN_EVERY_S * 0.75
        ch.tick(ch.next_at + 1)
        assert not ch.asking                       # nobody to ask outside the bathroom
        assert ch._present() == {}
    asyncio.run(scenario())


def test_tick_asks_the_character_in_the_house(ctx):
    async def scenario():
        ch = ctx.voice.chatter
        place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        script(ctx, ["sì"])
        now = time.monotonic()
        ch.tick(now)
        ch.tick(ch.next_at + 1)
        assert ch.asking
        await asyncio.gather(*list(ctx.voice._tasks))
        assert not ch.asking and ch.next_at > time.monotonic() + chatter_mod.MIN_EVERY_S * 0.7
        assert ctx.said and ctx.said[0][0].startswith("Marco,") and ctx.said[0][1] is True
        # never the same character twice in a row: alone in the house, Marco is not asked again
        assert ch._pick() is None
        place(ctx, "Anna", LIVING)
        assert ch._pick()[0] != ch.last_asked
    asyncio.run(scenario())


def test_no_question_while_the_house_is_busy_or_nobody_is_around(ctx):
    async def scenario():
        ch = ctx.voice.chatter
        ctx.settings.set("voice.verbosity", "chatty")
        place(ctx, "Marco", KITCHEN)
        now = time.monotonic()
        ctx.voice.last_chatter = now                # "Ecco Marco in cucina!": no question for 20 s
        assert not ch._ready(now)
        ctx.voice.last_chatter = now - 21
        assert ch._ready(now)
        async with ctx.voice.busy:
            assert not ch._ready(now)
        ctx.house.party_on = True
        assert not ch._ready(now)
        ctx.house.party_on = False
        ctx.voice.expect_entrance = {"name": "X", "until": time.time() + 30}
        assert not ch._ready(now)
        ctx.voice.expect_entrance["until"] = time.time() - 1       # expired: no longer in the way
        assert ch._ready(now)
        assert not ch._ready(now + chatter_mod.ACTIVE_S + 1)       # nobody around for 5 minutes
        ch.unanswered, ch.last_question = 2, now                   # two questions nobody answered
        assert not ch._ready(now + 1)
        ch.activity = now + 2                                      # a figurine moved: ask again
        assert ch._ready(now + 3)
        ctx.voice.mic.device = None
        ctx.voice.mic.follow = None
        assert not ch._ready(now + 3)              # no microphone: no question it could not hear
    asyncio.run(scenario())


def test_talk_stops_a_question(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        ch = ctx.voice.chatter

        async def waits(stop):
            await asyncio.sleep(10)                  # the visitor has not answered yet
            return "sì"
        script(ctx, [waits, ""])
        ch.asking = True
        task = ctx.voice._spawn(ch._ask(marco.id, question("k-hungry")))
        for _ in range(20):
            await asyncio.sleep(0)
        assert ch.active
        await ctx.voice.talk_button(True)            # Talk: the question stops, Talk gets the house
        await ctx.voice.talk_button(False)
        await asyncio.wait({task}, timeout=1)
        assert task.done() and not ch.asking and not ch.active
        await asyncio.gather(*list(ctx.voice._tasks), return_exceptions=True)
        assert not any(t.startswith("Allora apri il frigo") for t in texts(ctx))
    asyncio.run(scenario())


# ------------------------------------------------------------------ welcome
async def _settle(ctx):
    for _ in range(50):
        await asyncio.sleep(0)
        await asyncio.sleep(0.001)
        if not ctx.voice._tasks:
            return
    await asyncio.gather(*list(ctx.voice._tasks))


def test_a_new_phone_is_greeted_and_its_name_heard(ctx):
    async def scenario():
        script(ctx, ["ciao sono Luca", "sì"])
        ctx.bus.publish("phone_new", device="p-1", nickname=None)
        await _settle(ctx)
        assert texts(ctx) == [chatter_mod.WELCOME["it"], "Ti chiami Luca?", "Piacere, Luca! " + INVITE_IT]
        assert ctx.sent == [{"device": "p-1", "stage": "ask", "listening": True},
                            {"device": "p-1", "stage": "named", "name": "Luca"}]
        assert ctx.store.device("p-1")["nickname"] == "Luca"        # kept for a phone that was away
        ctx.sent.clear()
        ctx.bus.publish("phone_back", device="p-1", nickname=None)
        assert ctx.sent == [{"device": "p-1", "stage": "named", "name": "Luca"}]
    asyncio.run(scenario())


def test_a_name_typed_while_the_house_listens_wins(ctx):
    async def scenario():
        async def typed(stop):
            ctx.bus.publish("phone_named", device="p-2", name="Giulia")
            await asyncio.wait_for(stop.wait(), 1.0)       # the typed name ends the listening
            return ""
        script(ctx, [typed])
        ctx.bus.publish("phone_new", device="p-2", nickname=None)
        await _settle(ctx)
        assert texts(ctx)[-1] == "Piacere! " + INVITE_IT             # a typed name is not read aloud
        assert not any("Ti chiami" in t for t in texts(ctx))
    asyncio.run(scenario())


def test_noise_is_not_taken_for_a_name(ctx):
    async def scenario():
        async def noise(stop):
            return "e che"
        script(ctx, [noise])
        ctx.bus.publish("phone_new", device="p-8", nickname=None)
        await _settle(ctx)
        assert not any("Ti chiami" in t for t in texts(ctx))
        assert texts(ctx)[-1].startswith("Se vuoi, scrivi il tuo nome sul telefono.")
    asyncio.run(scenario())


def test_known_names_and_groups_of_phones(ctx):
    async def scenario():
        ctx.bus.publish("phone_new", device="p-3", nickname="Anna")
        await _settle(ctx)
        assert texts(ctx)[-1] == "Ciao! Si è collegato un telefono nuovo. " + INVITE_IT
        assert "Anna" not in texts(ctx)[-1]                            # typed on the phone: not read aloud
        assert ctx.sent[-1] == {"device": "p-3", "stage": "invite", "name": "Anna"}
        ctx.said.clear()
        ctx.sent.clear()
        ctx.bus.publish("phone_new", device="p-4", nickname=None)
        ctx.bus.publish("phone_new", device="p-5", nickname="Tom")
        await _settle(ctx)
        assert len(ctx.said) == 1 and "2 telefoni nuovi" in ctx.said[0][0] and "Tom" not in ctx.said[0][0]
        assert {"device": "p-4", "stage": "ask", "listening": False} in ctx.sent
    asyncio.run(scenario())


def test_one_spoken_welcome_at_a_time(ctx, monkeypatch):
    async def scenario():
        monkeypatch.setattr(chatter_mod, "GREET_GAP_S", 45.0)
        script(ctx, [])
        ctx.bus.publish("phone_new", device="p-10", nickname=None)
        await _settle(ctx)
        spoken = len(ctx.said)
        for i in range(5):                                   # a burst of new ids: cards only, no more speech
            ctx.bus.publish("phone_new", device=f"p-1{i + 1}", nickname=None)
            await _settle(ctx)
        assert len(ctx.said) == spoken
        assert sum(1 for m in ctx.sent if m["stage"] == "ask") == 6
        ctx.bus.publish("phone_named", device="p-11", name="Anna")      # thanks fall under the same limit
        await _settle(ctx)
        assert len(ctx.said) == spoken
    asyncio.run(scenario())


def test_typed_names_are_thanked_together_and_only_when_asked(ctx):
    async def scenario():
        script(ctx, [])
        ctx.bus.publish("phone_new", device="p-20", nickname=None)
        ctx.bus.publish("phone_new", device="p-21", nickname=None)
        await _settle(ctx)
        ctx.said.clear()
        ctx.bus.publish("phone_named", device="p-20", name="Anna")
        ctx.bus.publish("phone_named", device="p-21", name="Luca")
        ctx.bus.publish("phone_named", device="p-99", name="Spam")    # never asked: saved, not spoken
        await _settle(ctx)
        assert texts(ctx) == ["Piacere a tutti! Vi aspetto in casa con i vostri personaggi."]
        ctx.bus.publish("phone_named", device="p-20", name="Anna")     # a second time: nothing
        await _settle(ctx)
        assert len(ctx.said) == 1
    asyncio.run(scenario())


def test_a_name_typed_during_the_thanks_is_not_lost(ctx):
    async def scenario():
        script(ctx, [])
        ch = ctx.voice.chatter
        for d in ("p-50", "p-51"):
            ch._send(d, "ask", listening=False)
        ctx.bus.publish("phone_named", device="p-50", name="Anna")
        await asyncio.sleep(0)
        ctx.bus.publish("phone_named", device="p-51", name="Luca")     # while the first thanks is on its way
        await _settle(ctx)
        assert ch._thanks == 0 and len(ctx.said) >= 1
    asyncio.run(scenario())


def test_the_name_card_comes_back_once_after_a_reconnect(ctx):
    async def scenario():
        script(ctx, [])
        ctx.bus.publish("phone_new", device="p-30", nickname=None)
        await _settle(ctx)
        ctx.sent.clear()
        ctx.bus.publish("phone_back", device="p-30", nickname=None)
        assert ctx.sent == [{"device": "p-30", "stage": "ask", "listening": False}]
        ctx.bus.publish("phone_back", device="p-30", nickname=None)    # not at every reconnect
        ctx.bus.publish("phone_back", device="p-31", nickname=None)    # never asked
        assert len(ctx.sent) == 1
        ctx.bus.publish("phone_new", device="p-32", nickname=None)
        await _settle(ctx)
        ctx.bus.publish("phone_later", device="p-32")                  # "Later": the house stops asking
        ctx.sent.clear()
        ctx.bus.publish("phone_back", device="p-32", nickname=None)
        assert ctx.sent == []
    asyncio.run(scenario())


def test_names_cannot_inject_formats(ctx):
    line = ctx.actions.fill({"it": "Ciao {name}, sono le {time}"}, {"name": "{time}{room:>9}"}, "it")
    assert line.startswith("Ciao {time}{room:>9}, sono le ")
    assert ctx.actions.fill({"it": "Piacere, {name:>999999999}!"}, {}, "it") == "Piacere, {name:>999999999}!"


def test_silent_mode_asks_on_the_phone_only(ctx):
    async def scenario():
        ctx.settings.set("voice.verbosity", "silent")
        script(ctx, ["Marco"])
        ctx.bus.publish("phone_new", device="p-6", nickname=None)
        await _settle(ctx)
        assert ctx.sent[0] == {"device": "p-6", "stage": "ask", "listening": False}
        assert all(not spoken for _, spoken in ctx.said)
        assert not any("Ti chiami" in t for t in texts(ctx))      # it did not listen
    asyncio.run(scenario())


def test_greeting_can_be_turned_off(ctx):
    async def scenario():
        ctx.settings.set("voice.greet_phones", False)
        ctx.bus.publish("phone_new", device="p-7", nickname=None)
        await _settle(ctx)
        assert ctx.said == [] and ctx.sent == []
    asyncio.run(scenario())


# ------------------------------------------------------------------ web
def test_the_web_app_reports_new_phones_once(tmp_path):
    from fastapi.testclient import TestClient

    from domotiq.web.server import create_app
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera"]))
    seen, back, named, later = [], [], [], []
    c.bus.subscribe("phone_new", lambda ev: seen.append(dict(ev.data)))
    c.bus.subscribe("phone_back", lambda ev: back.append(dict(ev.data)))
    c.bus.subscribe("phone_named", lambda ev: named.append(dict(ev.data)))
    c.bus.subscribe("phone_later", lambda ev: later.append(dict(ev.data)))
    client = TestClient(create_app(c), headers={"X-Device": "p-web", "X-Nickname": ""})
    with client.websocket_connect("/ws?device=p-web&nick=") as ws:
        assert ws.receive_json()["type"] == "hello"
    with client.websocket_connect("/ws?device=p-web") as ws:
        ws.receive_json()
    with client.websocket_connect("/ws") as ws:               # the booth display: not a phone
        ws.receive_json()
    with client.websocket_connect("/ws?device=p-other&nick={x}") as ws:   # same address: the same phone
        ws.receive_json()
    assert seen == [{"device": "p-web", "nickname": None}]
    assert [b["device"] for b in back] == ["p-web", "p-other"] and back[1]["nickname"] == "x"
    r = client.post("/api/welcome", json={"name": "  Luca   Bianchi "})
    assert r.status_code == 200 and r.json()["name"] == "Luca Bianchi"
    assert named == [{"device": "p-web", "name": "Luca Bianchi"}]
    assert c.store.device("p-web")["nickname"] == "Luca Bianchi"
    assert client.post("/api/welcome", json={"name": " "}).status_code == 400
    assert client.post("/api/welcome", json={"later": True}).status_code == 200 and later == [{"device": "p-web"}]
    assert TestClient(create_app(c)).post("/api/welcome", json={"name": "X"}).status_code == 400
    c.store.close()


def test_the_welcome_goes_to_that_phone_only(tmp_path):
    from domotiq.web.server import Hub
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera"]))
    hub = Hub(c)
    mine, other = asyncio.Queue(), asyncio.Queue()
    hub.clients |= {mine, other}
    hub.attach("p-a", mine)
    hub.attach("p-b", other)
    hub.on_event(Event("welcome", {"device": "p-a", "stage": "ask"}))
    assert mine.qsize() == 1 and other.qsize() == 0
    hub.detach("p-a", mine)
    hub.on_event(Event("welcome", {"device": "p-a", "stage": "ask"}))
    assert mine.qsize() == 1 and "p-a" not in hub.devices
    hub.on_event(Event("heard", {"text": "whatever the microphone heard"}))
    assert mine.qsize() == 1 and other.qsize() == 0      # transcripts never go to the phones
    c.store.close()


def test_clean_names_and_forgotten_phones(tmp_path):
    from domotiq.identities import clean_name
    from domotiq.store import EVENT_RETENTION_S, Store
    assert clean_name("  {name:>9}\n Anna ") == "name:>9 Anna"
    st = Store(tmp_path / "db.sqlite")
    st.see_device("p-old", "Anna", now=1000.0)
    st.see_device("p-new", "Luca", now=1000.0 + EVENT_RETENTION_S + 10)
    st.purge(now=1000.0 + EVENT_RETENTION_S + 20)
    assert st.device("p-old") is None and st.device("p-new")["nickname"] == "Luca"
    st.close()


def test_a_quick_answer_is_heard_while_the_house_ends_its_question(ctx):
    """The microphone is open before the house has finished: its own voice is dropped, and an answer said
    right after the last word is kept."""
    v = ctx.voice
    fed = []

    class Session:
        def feed(self, chunk):
            fed.append(chunk)

        def result(self):
            return ("sì" if fed else ""), 1.0

    v.listener = SimpleNamespace(ok=True, session=lambda lang, grammar: Session())
    speaking = {"on": True}

    class Mic:
        available, last_level = True, 0.0

        async def listen(self, stop, on_chunk, max_s=60.0, min_s=0.0):
            for i in range(60):                      # 0.1 s chunks: the house speaks for 0.5 s more
                if stop.is_set():
                    break
                speaking["on"] = i < 5
                self.last_level = 0.3 if 9 <= i < 12 else 0.001    # "sì", 0.4 s after the house ended
                on_chunk(bytes([i]) * 4)
                await asyncio.sleep(0.1)
            return b""
    v.mic = Mic()

    async def scenario():
        return await v._listen(None, max_s=3.0, hold=lambda: speaking["on"], echo=0.3)
    text, _, audio = asyncio.run(scenario())
    assert text == "sì"
    # the house (chunks 0-4) and its echo (0.3 s after) are not in what is recognized; the answer is
    assert fed and fed[0][0] == 7 and audio[0] == 7 and 9 in audio


def test_a_word_of_the_list_counts_when_the_free_recognition_gets_it_wrong():
    from domotiq.voice.chatter import _trusted
    assert _trusted("gialla", 0.91, "già la")                  # nearly alike, or the list quite sure
    assert _trusted("sì", 0.84, "si sia")
    assert not _trusted("sì", 0.84, "")                         # nothing said: maybe a noise
    assert not _trusted("sì", 0.95, "che bella casa che avete")  # a whole sentence: something else
    assert not _trusted("mai", 0.5, "ciao")
