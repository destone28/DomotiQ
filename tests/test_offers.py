# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Offers of the house ("Ti va un po' di musica?", "Siete in tanti in soggiorno: facciamo festa?"): the answer is
understood, a yes runs what was offered and another command of the house runs that one instead."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from types import ModuleType, SimpleNamespace

import pytest

from domotiq.app import build, parse_args
from domotiq.voice import chatter as chatter_mod
from domotiq.voice import offers
from domotiq.voice.chatter import QUESTIONS
from domotiq.voice.intents import Intent

KITCHEN, LIVING, BEDROOM, GARDEN = (80, 100), (300, 100), (527, 170), (80, 300)
PARTY, GRILL, CINEMA = Intent("party"), Intent("grill"), Intent("scene", {"scene": "cinema"})


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(chatter_mod, "ECHO_S", 0.0)
    monkeypatch.setattr(chatter_mod, "GENERATED_SHARE", 0.0)
    monkeypatch.setattr(chatter_mod, "THINKING_S", 0.01)
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    c.voice.listener = SimpleNamespace(ok=True)      # as if the speech model and the microphone were there
    c.voice.mic.device = "test"
    c.said = []
    c.bus.subscribe("say", lambda ev: c.said.append(ev.get("text")))
    v = c.voice

    async def speak(*args, **kwargs):               # like the real one, without Piper
        v.in_flight += 1
        await asyncio.sleep(0)
        v.in_flight -= 1
        v.voice_end = time.monotonic()
    v.speak = speak
    c.done = []

    async def party():
        c.done.append("party")
        return True

    async def grill(duration_s=None, quiet=False):
        c.done.append("grill")
        return True
    c.actions.party, c.actions.grill = party, grill
    c.settings.set("voice.verbosity", "chatty")
    yield c
    c.store.close()


def script(ctx, answers, free=None):
    """The microphone hears these answers, one per listen: what the list of words heard, and (`free`, one per
    listen) what the free recognition of the same audio says; by default the same."""
    queue, frees = list(answers), list(free) if free is not None else None
    last = {"text": ""}

    async def listen(grammar_words, *, stop=None, max_s=5.0, auto_end=True, **_):
        item = queue.pop(0) if queue else ""
        last["text"] = item
        last["free"] = frees.pop(0) if frees else item
        return item, 1.0 if item else 0.0, b"x" if item or last["free"] else b""

    async def recognize(audio, grammar_words):
        return last["free"], 1.0 if last["free"] else 0.0
    ctx.voice._listen = listen
    ctx.voice._recognize = recognize


def place(ctx, name, where, category="person"):
    ident = ctx.identities.add(name, category)
    ctx.sim.add(*where, category, ident.id, "#e03030", name)
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    return ident


def question(qid):
    return next(q for q in QUESTIONS if q["id"] == qid)


def outcome(ctx):
    return ctx.store.events(types=["chatter"])[0]["data"]


# ------------------------------------------------------------------ the rules
@pytest.mark.parametrize("lang,offer,text,kind", [
    ("it", PARTY, "sì", "yes"), ("it", PARTY, "si dai mettiamo un po di musica", "yes"),
    ("it", PARTY, "certo che sì", "yes"), ("it", PARTY, "magari", "yes"), ("it", PARTY, "perché no", "yes"),
    ("it", PARTY, "o che facciamo festa", "yes"), ("it", PARTY, "volentieri", "yes"), ("it", PARTY, "dai", "yes"),
    ("it", PARTY, "dai andiamo", "yes"), ("it", PARTY, "mi piace la musica", "yes"),
    ("it", PARTY, "non vedo l'ora", "yes"), ("it", PARTY, "si mette la musica", "yes"),
    ("it", PARTY, "no grazie", "no"), ("it", PARTY, "non adesso", "no"), ("it", PARTY, "certo che no", "no"),
    ("it", PARTY, "non ho voglia di ballare", "no"), ("it", PARTY, "no niente musica", "no"),
    ("it", PARTY, "spegni la musica", "no"), ("it", PARTY, "forse dopo", "no"), ("it", PARTY, "sì ma non adesso", "no"),
    ("it", PARTY, "andiamo via", "no"), ("it", PARTY, "no accendi il baby", "no"),
    ("it", PARTY, "non lo so", "unsure"), ("it", PARTY, "sei bellissima", "other"),
    ("it", PARTY, "chi c'è in cucina", "other"), ("it", PARTY, "che bello", None), ("it", PARTY, "", "silence"),
    ("it", GRILL, "non accendere il barbecue", "no"), ("it", GRILL, "il barbecue no", "no"),
    ("it", GRILL, "barbecue", "yes"), ("it", CINEMA, "guardiamo un film", "yes"),
    ("it", CINEMA, "mi piace la musica", "other"), ("it", CINEMA, "no mi piace la musica", "no"),
    ("en", PARTY, "yes", "yes"), ("en", PARTY, "why not", "yes"), ("en", PARTY, "of course", "yes"),
    ("en", PARTY, "of course not", "no"), ("en", PARTY, "go ahead", "yes"), ("en", PARTY, "I'd love to", "yes"),
    ("en", PARTY, "I like music", "yes"), ("en", PARTY, "maybe later", "no"), ("en", PARTY, "no thanks", "no"),
    ("en", PARTY, "not now", "no"), ("en", PARTY, "I'm fine", "no"), ("en", PARTY, "I don't know", "unsure"),
    ("en", PARTY, "you're funny", "other"),
])
def test_what_an_answer_to_an_offer_means(lang, offer, text, kind):
    answer = offers.by_rules(text, lang, offer, ["Marco"])
    assert (answer.kind if answer else None) == kind, text


@pytest.mark.parametrize("lang,offer,text,kind", [
    # the offered command refused, whatever yes words come with it
    ("it", GRILL, "dai non accendere il barbecue", "no"), ("it", GRILL, "certo ma non accendere il barbecue", "no"),
    ("en", GRILL, "please don't light the barbecue", "no"), ("en", GRILL, "please no barbecue", "no"),
    ("it", PARTY, "sì però niente musica", "no"), ("it", PARTY, "va bene ma niente musica", "no"),
    ("en", PARTY, "don't light the barbecue", "no"),
    # a yes phrase after a negation, going home, a compliment
    ("en", PARTY, "don't do it", "no"), ("en", PARTY, "please don't do it", "no"), ("en", PARTY, "not a good idea", "no"),
    ("en", PARTY, "that's not a good idea", "no"), ("en", PARTY, "let's go home", "no"), ("en", PARTY, "let's go", "yes"),
    ("en", PARTY, "you're great", "other"), ("en", PARTY, "you are so cool", "other"), ("it", PARTY, "sei forte, sì dai", "yes"),
    # the offered thing only talked about, or disliked
    ("it", CINEMA, "spegni la tv", "no"), ("it", PARTY, "odio la musica", "no"), ("it", PARTY, "la musica è troppo alta", "no"),
    ("it", GRILL, "il barbecue puzza", "no"), ("en", GRILL, "I hate the barbecue", "no"),
    ("it", PARTY, "ieri abbiamo fatto festa", None), ("en", GRILL, "we had a barbecue yesterday", None),
    ("it", CINEMA, "il cinema è chiuso", None), ("it", PARTY, "il barbecue è buono", None),
    ("it", PARTY, "un po' di musica", "yes"), ("it", PARTY, "facciamo festa", "yes"), ("en", GRILL, "light the barbecue", "yes"),
    ("it", PARTY, "barbecue", "command"), ("it", CINEMA, "buonanotte", "command"),
])
def test_refusals_and_statements_are_not_a_yes(lang, offer, text, kind):
    """A yes word does not beat a refusal of what was offered, and naming it in a statement asks for nothing:
    such sentences go to the language model (None)."""
    answer = offers.by_rules(text, lang, offer, ["Marco"])
    assert (answer.kind if answer else None) == kind, text


@pytest.mark.parametrize("lang,text,name,args,accepted", [
    ("it", "no, accendi il barbecue", "grill", {}, False),
    ("it", "metti la luce rossa in soggiorno", "lights_on", {"room": "living", "color": "red"}, False),
    ("it", "no guardiamo un film", "scene", {"scene": "cinema"}, False),
    ("it", "sì e accendi il barbecue", "grill", {}, True),
    ("it", "magari accendi il barbecue", "grill", {}, False),    # "magari" here is "maybe", not a yes
    ("en", "no, light the barbecue", "grill", {}, False),
    ("en", "turn the living room light red", "lights_on", {"room": "living", "color": "red"}, False),
])
def test_another_command_said_instead(lang, text, name, args, accepted):
    answer = offers.by_rules(text, lang, PARTY, [])
    assert answer.kind == "command" and answer.intent.name == name and answer.intent.args == args
    assert answer.accepted is accepted


def test_the_words_listened_for_after_an_offer():
    words = offers.grammar(PARTY, "it")
    assert {"sì", "perché no", "dai", "volentieri", "no", "più tardi", "festa", "musica"} <= set(words)
    assert "barbecue" in offers.grammar(GRILL, "it") and "barbecue" not in words
    assert {"yes", "why not", "no", "party", "music"} <= set(offers.grammar(PARTY, "en"))


def test_the_model_form_and_how_sure_it_was():
    assert offers.from_model("yes", 0.95).kind == "yes"
    assert offers.from_model("yes", 0.7).kind == "unsure"          # asked again: it would run something
    assert offers.from_model("no", 0.6).kind == "no"
    assert offers.from_model("no", 0.3).kind == "other"
    assert offers.from_model("other", 0.9).kind == "other" and offers.from_model("maybe") is None
    msgs = offers.messages("Marco, ti va un po' di musica?", "sarebbe bello")
    assert msgs[0]["role"] == "system" and msgs[-1]["content"].endswith("Answer: sarebbe bello")


# ------------------------------------------------------------------ the speech recognizer
def test_accented_words_stay_in_the_list_of_words(tmp_path, monkeypatch):
    """The small models have no word list: a word is known if building a grammar with it gives no warning.
    Accented words ("sì", "perché no") are written as they are, never as escapes the recognizer does not know."""
    fake = ModuleType("vosk")
    fake.SetLogLevel = lambda level: None

    def recognizer(model, rate, grammar=None):
        if grammar and "\\u" in grammar:            # Vosk does not decode escapes: an unknown word
            os.write(2, b"WARNING (VoskAPI:UpdateGrammarFst()) Ignoring word missing in vocabulary\n")
        return SimpleNamespace()
    fake.KaldiRecognizer = recognizer
    monkeypatch.setitem(sys.modules, "vosk", fake)
    from domotiq.voice.stt import Listener
    listener = Listener(tmp_path)
    listener._models["it"] = object()
    assert listener.known("sì", "it") and listener.known("perché no", "it") and listener.known("certo", "it")


# ------------------------------------------------------------------ chatty questions that are offers
def test_a_natural_yes_runs_the_offer(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, ["sì dai mettiamo un po' di musica"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == ["party"] and ctx.said[-1] == "Ottima idea, Anna!"
        assert outcome(ctx)["outcome"] == "yes" and outcome(ctx)["action"] == "party"
    asyncio.run(scenario())


def test_perche_no_is_a_yes_even_if_the_list_heard_only_no(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, ["no"], free=["perché no"])          # the list keeps "no", the free recognition has it all
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == ["party"]
    asyncio.run(scenario())


def test_a_short_word_the_free_recognition_got_wrong(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, ["certo"], free=["certa"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == ["party"]
    asyncio.run(scenario())


def test_a_word_of_the_list_out_of_noise_runs_nothing(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, ["sì"], free=[""])                    # the list heard "sì", the free recognition nothing
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == [] and outcome(ctx)["outcome"] == "none"
    asyncio.run(scenario())


def test_another_command_in_the_answer_runs_instead_of_the_offer(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, ["no"], free=["no accendi il barbecue"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == ["grill"]
        assert not any("silenzio" in t for t in ctx.said)         # not the reply to a no
        assert outcome(ctx)["outcome"] == "command" and outcome(ctx)["action"] == "grill"
    asyncio.run(scenario())


def test_a_light_said_with_no_room_is_the_light_of_the_room_asked_about(ctx):
    async def scenario():
        sara = place(ctx, "Sara", BEDROOM)
        script(ctx, ["no accendi la luce blu"])
        await ctx.voice.chatter._ask(sara.id, question("b-rest"))
        assert ctx.lights.state()["bedroom"]["color"] == "blue"
        assert ctx.said[-1] == "Fatto."
    asyncio.run(scenario())


def test_the_dim_light_offered_is_dim_and_said_once(ctx):
    async def scenario():
        sara = place(ctx, "Sara", BEDROOM)
        script(ctx, ["volentieri"])
        await ctx.voice.chatter._ask(sara.id, question("b-rest"))
        light = ctx.lights.state()["bedroom"]
        assert light["color"] == "warm" and light["brightness"] == 20
        assert ctx.said[-1].startswith("Ecco, luce tenue") and "Fatto." not in ctx.said
    asyncio.run(scenario())


def test_a_statement_in_a_chat_question_runs_no_command(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        script(ctx, ["mi piace la musica", "accendi il barbecue", "mi piace la musica"])
        await ctx.voice.chatter._ask(marco.id, question("k-dish"))       # what's your favourite dish?
        await ctx.voice.chatter._ask(marco.id, question("a-from"))       # where are you from?
        await ctx.voice.chatter._ask(marco.id, question("k-hungry"))     # are you hungry? (no offer)
        assert ctx.done == [] and ctx.lights.state()["kitchen"].get("source") != "manual"
        assert ctx.said[-1] == "Non ho capito bene, ma grazie, Marco!"
    asyncio.run(scenario())


def test_an_unclear_answer_is_asked_again(ctx):
    async def scenario():
        luca = place(ctx, "Luca", LIVING)
        script(ctx, ["boh", "sì"])
        await ctx.voice.chatter._ask(luca.id, question("l-film"))
        assert chatter_mod.AGAIN["it"] in ctx.said and ctx.house.scene == "cinema"
        assert ctx.said[-1] == "Luci da cinema, Luca!" and "Scenario Cinema." not in ctx.said
    asyncio.run(scenario())


def test_silence_after_yes_or_no_is_still_not_clear(ctx):
    async def scenario():
        luca = place(ctx, "Luca", LIVING)
        script(ctx, ["boh", ""])
        await ctx.voice.chatter._ask(luca.id, question("l-film"))
        assert ctx.house.scene != "cinema" and outcome(ctx)["outcome"] == "unclear"
        assert ctx.said[-1] == "Non ho capito bene, ma grazie, Luca!" and ctx.voice.chatter.unanswered == 0
    asyncio.run(scenario())


def test_an_offer_in_english(ctx):
    async def scenario():
        ctx.settings.set("voice.language", "en")
        anna = place(ctx, "Anna", LIVING)
        script(ctx, ["sure"], free=["sure let's party"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == ["party"] and ctx.said[-1] == "Great idea, Anna!"
    asyncio.run(scenario())


def test_the_language_model_is_asked_only_when_the_rules_cannot_tell(ctx):
    asked = []

    async def offer_answer(question_line, sentence):
        asked.append((question_line, sentence))
        return offers.Answer("yes", source="llm")
    ctx.voice.llm, ctx.voice.llm_ready = SimpleNamespace(offer_answer=offer_answer), True

    async def scenario():
        anna, tom = place(ctx, "Anna", LIVING), place(ctx, "Tom", GARDEN)
        script(ctx, ["sì"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert asked == [] and ctx.done == ["party"]
        script(ctx, ["abbiamo una fame"])
        await ctx.voice.chatter._ask(tom.id, question("o-grill"))
        assert asked == [("Tom, accendo il barbecue?", "abbiamo una fame")] and ctx.done == ["party", "grill"]
        ctx.voice.llm_ready = False             # just started, its instructions not read yet: not asked
        script(ctx, ["abbiamo una fame"])
        await ctx.voice.chatter._ask(tom.id, question("o-grill"))
        assert len(asked) == 1 and ctx.done == ["party", "grill"]
    asyncio.run(scenario())


def test_a_yes_the_model_is_not_sure_of_is_asked_again(ctx):
    async def offer_answer(question_line, sentence):
        return offers.from_model("yes", 0.7)
    ctx.voice.llm, ctx.voice.llm_ready = SimpleNamespace(offer_answer=offer_answer), True

    async def scenario():
        tom = place(ctx, "Tom", GARDEN)
        script(ctx, ["bella la casa", "no"])
        await ctx.voice.chatter._ask(tom.id, question("o-grill"))
        assert ctx.done == [] and chatter_mod.AGAIN["it"] in ctx.said
        assert ctx.said[-1] == "Va bene, sarà per la prossima grigliata."
    asyncio.run(scenario())


def test_all_the_lights_said_in_the_answer_to_an_offer_are_all_of_them(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        ran = []

        async def execute(intent):
            ran.append((intent.name, intent.args.get("room")))
        ctx.voice.execute = execute
        script(ctx, ["no, spegni tutte le luci"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ran == [("lights_off", None)]
        script(ctx, ["no, spegni la luce"])                 # no room said: the one of the offer
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ran[-1] == ("lights_off", "living")
    asyncio.run(scenario())


def test_talk_can_still_answer_an_offer_nobody_answered(ctx):
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, [""])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        assert ctx.done == []
        await ctx.voice.handle("sì")                    # Talk, a few seconds later
        assert ctx.done == ["party"]
        await ctx.voice.handle("sì")                    # once only: now a plain yes
        assert ctx.done == ["party"] and ctx.said[-1] == "D'accordo."
    asyncio.run(scenario())


def test_talk_after_an_offer_still_asks_other_things(ctx):
    """While an offer waits for Talk, a question or another request is not taken for its answer."""
    async def scenario():
        anna = place(ctx, "Anna", LIVING)
        script(ctx, [""])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))
        for text in ("non c'è nessuno in cucina?", "si può accendere la luce in cucina?", "si vede bene la casa"):
            assert not await ctx.voice.chatter.answer_by_talk(text), text
        assert ctx.done == []
        assert await ctx.voice.chatter.answer_by_talk("sì dai mettiamo la musica")
        assert ctx.done == ["party"]
    asyncio.run(scenario())


def test_a_new_question_closes_the_offer_left_open(ctx):
    async def scenario():
        anna, marco = place(ctx, "Anna", LIVING), place(ctx, "Marco", KITCHEN)
        script(ctx, ["", "pizza"])
        await ctx.voice.chatter._ask(anna.id, question("l-music"))       # nobody answers the music
        await ctx.voice.chatter._ask(marco.id, question("k-cook"))       # then pizza or pasta?
        await ctx.voice.handle("sì")
        assert ctx.done == []                           # "sì" is not for the music any more
    asyncio.run(scenario())


# ------------------------------------------------------------------ offers to a crowd
def crowd(ctx, room, n):
    ctx.bus.publish("count_changed", room=room, persons=n)


async def settle(ctx):
    for _ in range(100):
        await asyncio.sleep(0.005)
        if not any(not t.done() for t in ctx.voice._tasks):
            return


def test_a_crowd_in_the_living_room_is_offered_a_party_and_heard(ctx):
    async def scenario():
        script(ctx, ["sì volentieri"])
        crowd(ctx, "living", 3)
        await settle(ctx)
        assert ctx.said[0] == "Siete in tanti in soggiorno: facciamo festa?" and ctx.done == ["party"]
        ev = outcome(ctx)
        assert ev["question"] == "c-party" and ev["outcome"] == "yes" and ev["action"] == "party"
        crowd(ctx, "living", 4)                          # at most one every 10 minutes
        await settle(ctx)
        assert ctx.said.count("Siete in tanti in soggiorno: facciamo festa?") == 1
    asyncio.run(scenario())


def test_the_barbecue_offered_to_the_garden_and_a_no(ctx):
    async def scenario():
        script(ctx, ["no grazie"])
        crowd(ctx, "garden", 2)
        await settle(ctx)
        assert ctx.said == ["Che bella giornata in giardino: accendo il barbecue?",
                            "D'accordo, sarà per la prossima grigliata."]
        assert ctx.done == []
    asyncio.run(scenario())


def test_no_offer_to_a_crowd_while_the_house_is_busy_or_partying(ctx):
    async def scenario():
        script(ctx, ["sì"])
        ctx.house.party_on = True
        crowd(ctx, "living", 5)
        await settle(ctx)
        ctx.house.party_on = False
        async with ctx.voice.busy:
            crowd(ctx, "living", 5)
            await settle(ctx)
        assert ctx.said == [] and ctx.done == []
        ctx.settings.set("voice.verbosity", "normal")
        crowd(ctx, "living", 5)
        await settle(ctx)
        assert ctx.said == []
    asyncio.run(scenario())


def test_with_no_microphone_the_offer_to_a_crowd_waits_for_talk(ctx):
    async def scenario():
        ctx.voice.mic.device = None
        ctx.voice.mic.follow = None
        crowd(ctx, "living", 3)
        await settle(ctx)
        assert ctx.said == ["Siete in tanti in soggiorno: facciamo festa?"] and ctx.done == []
        await ctx.voice.handle("sì")                    # with Talk: a plain yes, for the party just offered
        assert ctx.done == ["party"]
    asyncio.run(scenario())


# ------------------------------------------------------------------ the language model
def test_the_offers_need_a_third_slot_of_the_language_model(monkeypatch):
    from domotiq.voice import llm as llm_mod
    model = llm_mod.LanguageModel()
    calls = []
    monkeypatch.setattr(model, "_offer", lambda q, s, timeout=None: (calls.append((q, s)), ("yes", 0.95))[1])

    async def ask():
        return await model.offer_answer("Facciamo festa?", "sarebbe bello")
    model.slots = 2                                      # the old service: it would take the slot of the commands
    assert asyncio.run(ask()) is None and calls == []
    model.slots = 3
    assert asyncio.run(ask()).kind == "yes" and calls == [("Facciamo festa?", "sarebbe bello")]
    warmed = []
    monkeypatch.setattr(model, "_ask", lambda *a, **k: warmed.append("commands"))
    monkeypatch.setattr(model, "_classify", lambda *a, **k: warmed.append("answers"))
    monkeypatch.setattr(model, "_offer", lambda *a, **k: warmed.append("offers"))
    model.warm()
    assert warmed == ["commands", "answers", "offers"]
    warmed.clear()
    model.slots = 2
    model.warm()
    assert warmed == ["commands", "answers"]
    assert json.loads(json.dumps(offers.GRAMMAR_GBNF)) == 'root ::= "yes" | "no" | "other"'


def test_the_instructions_are_put_back_from_the_last_start(monkeypatch):
    """Read once (minutes on the board), saved, and put back in a moment at the next start of llama-server; a slot
    shared by two instructions is neither saved nor put back."""
    from domotiq.voice import llm as llm_mod
    model = llm_mod.LanguageModel()
    files, calls, clock = {}, [], [0.0]

    def slot_file(action, slot, name):
        calls.append((action, name))
        if action == "save":
            files[name] = slot
        return name in files
    monkeypatch.setattr(model, "_slot_file", slot_file)
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: clock[0])

    def asked(name):
        def ask(*args, **kwargs):
            clock[0] += 0.5 if name in files else 120.0       # put back: a moment; read: two minutes
            return "other", 1.0
        return ask
    for method, name in (("_ask", "commands"), ("_classify", "answers"), ("_topic", "facts"), ("_offer", "offers")):
        monkeypatch.setattr(model, method, asked(name))
    model.slots = 4
    model.warm()                                              # the first start: read and saved
    assert clock[0] == 480.0 and files == {"commands": 0, "answers": 1, "facts": 3, "offers": 2}
    calls.clear()
    model.warm()                                              # the next start: put back
    assert clock[0] == 482.0 and all(action == "restore" for action, _ in calls) and len(calls) == 4
    files.clear()
    calls.clear()
    model.slots = 3                                           # the topics share the slot of "who is it?"
    model.warm()
    assert sorted(files) == ["commands", "offers"] and ("restore", "answers") not in calls


def test_a_new_start_of_llama_server_is_noticed(monkeypatch):
    """Started again between two checks, llama-server has an empty cache: the slot of the commands tells."""
    import io
    from domotiq.voice import llm as llm_mod
    model = llm_mod.LanguageModel()
    answers = {}

    def urlopen(url, timeout=None):
        url = url if isinstance(url, str) else url.full_url
        if url not in answers:
            raise OSError("no such page")
        return io.BytesIO(json.dumps(answers[url]).encode())
    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", urlopen)
    answers[model.url + "/slots"] = [{"id": 0}, {"id": 1}]                       # just started
    assert model._cold()
    answers[model.url + "/slots"] = [{"id": 0, "n_prompt_tokens": 1535}, {"id": 1}]
    assert not model._cold()
    del answers[model.url + "/slots"]                                            # no list of the slots
    assert not model._cold()

