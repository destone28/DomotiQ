# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Stories, memories of the day and facts about the characters, with a fake story model."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from domotiq.app import build, parse_args
from domotiq.voice import memory
from domotiq.voice.intents import Intent

KITCHEN, LIVING = (80, 100), (300, 100)


class FakeModel:
    """Answers like llama-server would, and remembers what it was asked."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.slots: list[int] = []
        self.rate = 10.0                            # tokens a second: fast enough to speak while writing
        self.personas = 0
        self.story = ("Marco trovò un pacco in garage. Dentro c'era una tromba d'oro. "
                      "Suonò in cucina e tutti ballarono. Fu una serata bellissima.")
        self.question = "D: Marco, hai pagato la bolletta della luce?\nSI: Bravo, sei il più preciso della casa!\nNO: Allora corri, scade domani!"

    def health(self) -> bool:
        return True

    def _text(self, grammar):
        if grammar and "SI:" in grammar:
            return self.question
        if grammar:
            self.personas += 1
            return "lavoro: medico; carattere: distratto; passione: il jazz; mania: parla alle piante"
        return self.story

    def stream(self, messages, tokens, temperature=0.8, grammar=None, stop=None, slot=0):
        self.asked.append("\n".join(m["content"] for m in messages))
        self.slots.append(slot)
        text = self._text(grammar) if tokens > 1 else ""
        for word in text.split(" "):
            if stop is not None and stop.is_set():
                return
            yield word + " "

    def complete(self, messages, tokens, temperature=0.7, grammar=None, stop=None, slot=0):
        return "".join(self.stream(messages, tokens, temperature, grammar, stop, slot))


@pytest.fixture
def ctx(tmp_path):
    c = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera", "--no-llm"]))
    from domotiq.voice.manager import Voice
    c.voice = Voice(c)
    c.model = FakeModel()
    c.voice.stories.model = c.model
    c.voice.stories.ok = True
    c.said = []
    c.bus.subscribe("say", lambda ev: c.said.append(ev.get("text")))

    c.voices = []                                   # (sentence, language of the voice) as synthesized

    async def speak(*args, **kwargs):
        await asyncio.sleep(0)

    async def synth(text, lang):
        c.voices.append((text, lang))
        return [0.0] * 10

    async def play(samples):
        await asyncio.sleep(c.play_s)
    c.play_s = 0.0
    c.voice.speak = speak
    c.voice.speaker.synth = synth
    c.voice.play = play
    yield c
    c.store.close()


def place(ctx, name, where, category="person"):
    ident = ctx.identities.add(name, category)
    ctx.sim.add(*where, category, ident.id, "#e03030", name)
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    return ident


def test_a_story_is_spoken_sentence_by_sentence(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        assert await ctx.voice.stories.tell(["Marco"])
        assert ctx.said[0] == "Fammi pensare..."
        assert ctx.said[1:] == ["Marco trovò un pacco in garage.", "Dentro c'era una tromba d'oro.",
                                "Suonò in cucina e tutti ballarono.", "Fu una serata bellissima."]
        assert ctx.lights.state()["kitchen"]["source"] in ("auto", "off", "follow")      # back to normal at the end
        assert ctx.store.events(types=["story"])[0]["data"]["cast"] == ["Marco"]
    asyncio.run(scenario())


def test_a_character_keeps_its_personality_until_the_restart(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        st = ctx.voice.stories
        await st.tell(["Marco"])
        await st.tell(["Marco"])
        assert ctx.model.personas == 1                      # made up once, then kept
        assert "lavoro: medico; carattere: distratto" in ctx.model.asked[-1]   # the second story knows who Marco is
        # a story already told is not told again
        assert "Già raccontate, non ripeterle" in ctx.model.asked[-1] and "Marco trovò un pacco" in ctx.model.asked[-1]
        st.reset()                                          # what a restart does
        await st.tell(["Marco"])
        assert ctx.model.personas == 2
    asyncio.run(scenario())


def test_the_facts_of_the_staff_come_first(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        st = ctx.voice.stories
        await st.tell(["Marco"])
        assert ctx.model.personas == 1
        ctx.identities.update(marco.id, facts=["fa il pompiere"])
        await st.tell(["Marco"])
        assert ctx.model.personas == 2                      # remade, keeping the new fact
        persona_prompt = next(a for a in reversed(ctx.model.asked) if "personalità di Marco" in a)
        assert "Deve rispettare: fa il pompiere" in persona_prompt
        assert "fatti certi fa il pompiere" in ctx.model.asked[-1]
    asyncio.run(scenario())


def test_what_the_house_makes_up_is_remembered(ctx):
    async def scenario():
        st = ctx.voice.stories
        ctx.model.story = "L'assicurazione dell'auto scade il dieci marzo."
        await st.answer("quando scade l'assicurazione dell'auto")
        assert ctx.said[-1] == "L'assicurazione dell'auto scade il dieci marzo."
        await st.answer("e quanto costa l'assicurazione")
        assert "scade il dieci marzo" in ctx.model.asked[-1]      # the next answer agrees with it
    asyncio.run(scenario())


def test_stories_and_answers_in_english(ctx):
    async def scenario():
        ctx.settings.set("voice.language", "en")
        place(ctx, "Marco", KITCHEN)
        ctx.model.story = "Marco found a parcel. It was a golden trumpet."
        await ctx.voice.stories.tell(["Marco"])
        assert ctx.said[0] == "Let me think..."
        assert any("A new story, at most five sentences" in a for a in ctx.model.asked)
        assert any("Make up the personality of Marco" in a for a in ctx.model.asked)
    asyncio.run(scenario())


def test_blocked_words_are_never_said(ctx):
    async def scenario():
        ctx.model.story = "Marco entrò in cucina. Poi disse una parolaccia: merda! Alla fine risero tutti."
        place(ctx, "Marco", KITCHEN)
        await ctx.voice.stories.tell(["Marco"])
        assert not any("merda" in s for s in ctx.said)
        assert "Alla fine risero tutti." in ctx.said
    asyncio.run(scenario())


def test_facts_by_voice_and_what_the_house_knows(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        await ctx.voice.execute(Intent("fact", {"name": "Marco", "text": "ricorda che marco fa il medico"}))
        assert ctx.identities.get(marco.id).facts == ["fa il medico"]
        assert ctx.said[-1] == "Me lo ricorderò: Marco fa il medico."
        text = await ctx.voice.stories.about("Marco")
        assert text.startswith("Di Marco so questo: fa il medico") and "distratto" in text
    asyncio.run(scenario())


def test_talk_stops_a_story(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        ctx.model.story = " ".join(f"Frase numero {i} della storia." for i in range(40))
        v = ctx.voice

        ctx.play_s = 0.2

        async def listen(grammar, *, stop=None, max_s=5.0, auto_end=True):
            return "", 0.0, b""
        v._listen = listen
        v._talk_task = v._spawn(v.execute(Intent("story", {"names": ["Marco"]})))
        for _ in range(30):
            await asyncio.sleep(0.01)
        assert v.stories.active
        await v.talk_button(True)
        assert v._talk_task.done() is False or not v.stories.active
        await v.talk_button(False)
        await asyncio.gather(*list(v._tasks), return_exceptions=True)
        assert len([s for s in ctx.said if s.startswith("Frase numero")]) < 4     # stopped halfway
    asyncio.run(scenario())


def test_a_generated_chatty_question_is_answered(ctx):
    async def scenario():
        from domotiq.voice import chatter as chatter_mod
        chatter_mod.ECHO_S = 0.0
        marco = place(ctx, "Marco", KITCHEN)
        ctx.settings.set("voice.verbosity", "chatty")
        ctx.voice.listener = SimpleNamespace(ok=True)
        ctx.voice.mic.device = "test"
        answers = iter(["sì"])

        async def listen(grammar, *, stop=None, max_s=5.0, auto_end=True):
            text = next(answers, "")
            return text, 1.0, b"x" if text else b""

        async def recognize(audio, grammar):
            return "sì", 1.0
        ctx.voice._listen, ctx.voice._recognize = listen, recognize
        await ctx.voice.chatter._ask(marco.id, {"id": "gen-question", "kind": "generated", "gen": "question"})
        assert ctx.said[0] == "Marco, hai pagato la bolletta della luce?"
        assert ctx.said[1] == "Bravo, sei il più preciso della casa!"        # the reply written with the question
        assert any("Marco: sì" in item for item in ctx.voice.stories.lore)
        ev = ctx.store.events(types=["chatter"])[0]["data"]
        assert ev["question"] == "gen-question" and ev["outcome"] == "answered" and "heard" not in ev
    asyncio.run(scenario())


def test_stories_are_written_ahead_and_told_at_once(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        st = ctx.voice.stories
        for _ in range(6):                          # personality, memory of the house, Marco's story, any story
            await st._ahead_step()
        assert f"story:{marco.id}" in st.ahead and "story:*" in st.ahead
        assert all(slot == 1 for slot, asked in zip(ctx.model.slots, ctx.model.asked) if "Storia nuova" in asked)
        asked_before = len(ctx.model.asked)
        await st.tell(["Marco"])
        assert "Fammi pensare..." not in ctx.said                   # no waiting: it was ready
        assert ctx.said[0] == "Marco trovò un pacco in garage."
        assert len(ctx.model.asked) == asked_before                 # nothing asked to the model meanwhile
        assert f"story:{marco.id}" not in st.ahead                  # used: the next one will be different
        ctx.identities.update(marco.id, facts=["fa il pompiere"])
        await st._ahead_step()
        assert not any(marco.id in v["cast"] for v in st.ahead.values())   # written with the old facts: thrown away
    asyncio.run(scenario())


def test_the_memory_of_the_house_is_given_to_every_free_answer(ctx):
    async def scenario():
        marco = place(ctx, "Marco", KITCHEN)
        ctx.identities.update(marco.id, facts=["fa il medico"])
        st = ctx.voice.stories
        ctx.model.story = "Sì, Marco le ha pagate lunedì."
        await st.answer("Marco ha pagato le bollette?", ["Marco"])
        asked = ctx.model.asked[-1]
        assert "Memoria della casa" in asked and "fatti certi fa il medico" in asked
        await st.answer("e quando scadono le prossime?")
        assert "le ha pagate lunedì" in ctx.model.asked[-1]
        assert all(slot == 0 for slot in ctx.model.slots[-2:])         # the slot that keeps the memory read
    asyncio.run(scenario())


def test_sentences_split_well():
    from domotiq.voice.stories import split_sentences
    done, rest = split_sentences("Lived Mr. Smith in a house. Dott. Rossi arrived! And then")
    assert done == ["Lived Mr. Smith in a house.", "Dott. Rossi arrived!"] and rest == "And then"


# ------------------------------------------------------------------ memories of the day
def test_what_a_character_did_today(ctx):
    marco = ctx.identities.add("Marco", "person")
    t0 = time.time() - 1800
    rows = [(t0 + s, "v1", marco.id, 80, 100, "kitchen") for s in range(0, 600, 5)]
    rows += [(t0 + 600 + s, "v1", marco.id, 300, 100, "living") for s in range(0, 300, 5)]
    rows += [(t0 + 900 + s, "v1", marco.id, 500, 100, "bedroom") for s in range(0, 100, 5)]
    ctx.store.add_positions(rows)
    ctx.store.add_event("party", {"state": "started"}, ts=t0 + 700)
    ctx.clock.source = "staff"                     # the house knows the time: "today" starts at midnight
    text = memory.day_of(ctx, "Marco", "it", now=t0 + 1000)
    assert "per la prima volta" in text and "Ha passato più tempo in cucina" in text
    assert "poi in soggiorno e in camera" in text and "una festa" in text
    en = memory.day_of(ctx, "Marco", "en", now=t0 + 1000)
    assert "spent most of the time in the kitchen" in en and "a party" in en
    assert "Marco" in memory.room_day(ctx, "kitchen", "it", now=t0 + 1000)
    assert "una festa" in memory.parties_today(ctx, "it", now=t0 + 1000)
    assert memory.day_of(ctx, "Nessuno", "it").startswith("Non conosco")


def test_each_sentence_is_read_by_the_voice_of_its_language(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        ctx.model.story = ("Marco entrò in cucina con una torta. Then he saw that the cake was gone and the kitchen was "
                           "empty. Alla fine la torta era nel frigo.")
        await ctx.voice.stories.tell(["Marco"])
        voices = dict(ctx.voices)
        assert voices["Marco entrò in cucina con una torta."] == "it"
        assert voices["Then he saw that the cake was gone and the kitchen was empty."] == "en"
        assert voices["Alla fine la torta era nel frigo."] == "it"
    asyncio.run(scenario())


def test_a_story_stops_when_the_language_changes(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        ctx.model.story = " ".join(f"Frase numero {i} della storia." for i in range(40))
        ctx.play_s = 0.2
        v = ctx.voice
        task = v._spawn(v.execute(Intent("story", {"names": ["Marco"]})))
        for _ in range(30):
            await asyncio.sleep(0.01)
        await ctx.actions.set_language("en")
        await asyncio.wait({task}, timeout=2)
        assert task.done()
        assert len([s for s in ctx.said if s.startswith("Frase numero")]) < 4
    asyncio.run(scenario())


def test_a_slow_model_promises_the_story_and_tells_it_later(ctx):
    async def scenario():
        place(ctx, "Marco", KITCHEN)
        ctx.model.rate = 1.0                        # like a big model on the UNO Q: slower than speech
        st = ctx.voice.stories
        assert st.slow
        assert await st.tell(["Marco"])
        assert ctx.said[-1] == "La sto ancora scrivendo: te la racconto tra un paio di minuti!"
        await asyncio.gather(*list(ctx.voice._tasks))
        assert "Ecco la storia che mi avevi chiesto!" in ctx.said
        assert ctx.said[-1] == "Fu una serata bellissima."
        ctx.model.story = "Sì, Marco le ha pagate lunedì."
        assert await st.answer("Marco ha pagato le bollette?", ["Marco"])
        assert ctx.said[-1] == "Bella domanda! Ci penso e te lo dico tra poco."
        await asyncio.gather(*list(ctx.voice._tasks))
        assert ctx.said[-2:] == ["Ecco la risposta alla domanda di prima.", "Sì, Marco le ha pagate lunedì."]
        assert any("pagate lunedì" in item for item in st.lore)
    asyncio.run(scenario())
