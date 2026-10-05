# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The word of activation in place of Talk, and the LEDs of the buttons: steady while the house speaks, blinking
while it listens."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from domotiq.voice import variants as V
from domotiq.voice.intents import spoken
from test_offers import KITCHEN, ctx, place, script  # noqa: F401 - the fixture


PROMPTS = {it for it, _ in V.WAKE_PROMPT}


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

        async def handle(text, **kw):
            handled.append(text)
        v.handle = handle
        await v._woken("che ore sono")                         # "Casa, che ore sono?": all at once
        assert handled == ["che ore sono"] and not ctx.said
        script(ctx, ["accendi la luce in cucina"])
        await v._woken("")                                     # "Casa": the house asks, then listens
        assert ctx.said[-1] in PROMPTS and handled[-1] == "accendi la luce in cucina"
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


class _Mic:
    """Chunks of 100 ms, each with the words said in it (<casa>) and its level."""
    available = True

    def __init__(self, chunks, log):
        self.chunks, self.log, self.last_level = chunks, log, 0.0

    async def listen(self, stop, on_chunk=None, max_s=60.0, min_s=0.0):
        for i, (chunk, level) in enumerate(self.chunks):
            if stop.is_set():
                break
            self.last_level = level
            self.log.append(("chunk", i))
            on_chunk(chunk)
            await asyncio.sleep(0.005)
        return b""


class _Session:
    def __init__(self, grammar):
        self.grammar, self.heard = grammar, []

    def _words(self, pcm):
        import re
        return [w.decode() for w in re.findall(rb"<(\w*)>", pcm) if w]

    def feed(self, pcm):
        self.heard += self._words(pcm)

    def feed_partial(self, pcm):
        self.heard += self._words(pcm)
        # held to the word, the recognizer takes anything like it for the word
        return " ".join("casa" if w in ("casa", "cosa") else "[unk]" for w in self.heard)

    def sureness(self, phrase):
        return 0.9

    def result(self):
        return " ".join(self.heard), 0.9

    def alternatives(self):
        return [" ".join(self.heard)]


class _Listener:
    ok = True

    def session(self, lang, grammar=None, respell=True, alternatives=0):
        return _Session(grammar)

    def known(self, word, lang):
        return True


def _said(*words, pause=0, then=(), quiet=20):
    out = [(b"<>", 0.0)] * 3 + [(f"<{w}>".encode(), 0.1) for w in words]
    out += [(b"<>", 0.0)] * pause + [(f"<{w}>".encode(), 0.1) for w in then]
    return out + [(b"<>", 0.0)] * quiet


def test_the_word_lights_the_leds_at_once_and_the_request_said_with_it_is_heard(ctx):
    async def scenario():
        v = ctx.voice
        log = []

        async def leds(mask, blink=0):
            log.append(("leds", mask, blink))
        ctx.mcu.leds = leds
        v.listener = _Listener()
        v.mic = _Mic(_said("casa", "accendi", "la", "luce", "in", "cucina"), log)
        woke, rest = await v._wake_listen("casa")
        assert woke and rest == "accendi la luce in cucina" and v.busy.locked()
        v.busy.release()
        await ctx.actions.thinking(False)
        # blinking as soon as the word is heard (the 4th chunk), long before the sentence ends
        blink = log.index(("leds", 7, 7))
        assert max(e[1] for e in log[:blink] if e[0] == "chunk") <= 5
        # a short pause after the word, and then the request: still heard
        log.clear()
        v.mic = _Mic(_said("casa", pause=2, then=("che", "ore", "sono")), log)
        assert await v._wake_listen("casa") == (True, "che ore sono")
        v.busy.release()
        await ctx.actions.thinking(False)
        # a longer one: the house does not keep you waiting, it answers ("Dimmi!") and listens
        v.mic = _Mic(_said("casa", pause=8, then=("che", "ore", "sono")), log)
        assert await v._wake_listen("casa") == (True, "")
        v.busy.release()
        # the word alone: the house asks what is needed
        v.mic = _Mic(_said("casa", quiet=25), log)
        assert await v._wake_listen("casa") == (True, "")
        v.busy.release()
        # talk near the house: held to the word the recognizer took "cosa" for it, the free one did not
        log.clear()
        v.mic = _Mic(_said("cosa", "facciamo", "stasera"), log)
        assert await v._wake_listen("casa") == (False, "")
        assert not v.busy.locked() and log[-1] == ("leds", 0, 0)
    asyncio.run(scenario())


def test_after_the_word_the_house_is_already_taken(ctx):
    async def scenario():
        v = ctx.voice
        handled = []

        async def handle(text, **kw):
            handled.append((text, v.busy.locked()))
        v.handle = handle
        await v.busy.acquire()                                 # taken when the word was heard
        await v._woken("che ore sono", held=True)
        assert handled == [("che ore sono", True)] and not v.busy.locked()
        script(ctx, ["spegni la luce"])
        await v._woken("ehm")                                  # a noise after the word: not a request
        assert ctx.said[-1] in PROMPTS and handled[-1] == ("spegni la luce", True)
    asyncio.run(scenario())


def test_a_list_of_words_and_the_free_recognition_at_the_same_time(ctx):
    async def scenario():
        v = ctx.voice
        made = []

        class Listener(_Listener):
            def session(self, lang, grammar=None, respell=True, alternatives=0):
                s = _Session(grammar)
                made.append(s)
                return s
        v.listener = Listener()
        v.mic = _Mic(_said("direi", "di", "si", quiet=10), [])
        text, conf, audio = await v._listen(["si", "no"], max_s=5.0)
        assert len(made) == 2 and made[1].grammar is None                   # the free one, fed at the same time
        assert made[0].heard == made[1].heard == ["direi", "di", "si"]
        free, _ = await v._recognize(audio, None)                           # ready: nothing recognized again
        assert free == "direi di si" and len(made) == 2
        v.mic = _Mic(_said("si", quiet=10), [])
        await v._listen(None, max_s=5.0)
        assert len(made) == 3                                               # free speech: one recognizer
    asyncio.run(scenario())


def test_a_name_the_free_recognition_gets_wrong_is_heard_by_the_list_of_names(ctx):
    """"Dov'è l'Honda Civic?" heard as "dovevo music": the recognizer that knows only the names hears the car."""
    import time

    async def scenario():
        v = ctx.voice
        car = ctx.identities.add("Honda Civic", "car")
        ctx.sim.add(540, 300, "car", car.id, "#c02020", "Honda Civic")
        ctx.house.update_tracks(ctx.sim.tracks(), time.time())

        class Session(_Session):
            def result(self):
                return ("dovevo music", 0.8) if self.grammar is None else ("honda civic", 0.9)

        class Listener(_Listener):
            def session(self, lang, grammar=None, respell=True, alternatives=0):
                return Session(grammar)
        v.listener = Listener()
        v.mic = _Mic(_said("dov", "e", "honda", "civic"), [])
        text, conf, audio = await v._listen(None, max_s=5.0, names=True)
        assert text == "dovevo music"
        await v.handle(text, spotted=v._spotted_for(audio))
        assert ctx.said[-1] == "Honda Civic è in garage."
    asyncio.run(scenario())


def test_a_request_is_understood_in_an_alternative_and_an_unknown_name_by_the_list(ctx):
    """"Chi c'è in cucina?" heard as "di già in cucina": the second sentence the recognizer found likely is taken.
    "Dov'è Mister Green?" heard as "dov'è misteri", a name the house does not know: the list of names heard it."""
    import time

    async def scenario():
        v = ctx.voice
        green = ctx.identities.add("Mister Green", "person")
        ctx.sim.add(120, 120, "person", green.id, "#20c020", "Mister Green")
        ctx.house.update_tracks(ctx.sim.tracks(), time.time())
        heard = {"free": ("di già in cucina", 0.4), "alternatives": ["di già in cucina", "chi c'è in cucina"],
                 "names": ("", 0.0)}

        class Session(_Session):
            def result(self):
                return heard["free"] if self.grammar is None else heard["names"]

            def alternatives(self):
                return heard["alternatives"]

        made = []

        class Listener(_Listener):
            def session(self, lang, grammar=None, respell=True, alternatives=0):
                made.append(alternatives)
                return Session(grammar)
        v.listener = Listener()
        v.mic = _Mic(_said("chi", "c", "e", "in", "cucina"), [])
        text, conf, audio = await v._listen(None, max_s=5.0, names=True)
        assert made[0] == 5                                   # a request: its alternatives are kept
        await v.handle(text, spotted=v._spotted_for(audio), alternatives=v._alternatives_for(audio))
        assert "Mister Green" in ctx.said[-1] and "cucina" in ctx.said[-1]

        heard.update({"free": ("dov'è misteri", 0.8), "alternatives": ["dov'è misteri"],
                      "names": ("mister green", 0.9)})
        v.mic = _Mic(_said("dov", "e", "mister", "green"), [])
        text, conf, audio = await v._listen(None, max_s=5.0, names=True)
        await v.handle(text, spotted=v._spotted_for(audio), alternatives=v._alternatives_for(audio))
        assert ctx.said[-1] == "Mister Green è in cucina."
    asyncio.run(scenario())


def test_the_word_alone_is_answered_at_once(ctx):
    """"Ambrogio" and nothing after it: the house answers half a second later, without waiting for the free
    recognizer, and the LEDs never go off in between."""
    async def scenario():
        v = ctx.voice
        log = []

        async def leds(mask, blink=0):
            log.append(("leds", mask, blink))
        ctx.mcu.leds = leds

        class Session(_Session):
            def result(self):
                if self.grammar is None:
                    raise AssertionError("the free recognizer is not waited for")
                return super().result()
        v.listener = type("L", (_Listener,), {"session": lambda self, lang, grammar=None, respell=True, alternatives=0: Session(grammar)})()
        v.mic = _Mic(_said("casa", quiet=30), log)
        assert await v._wake_listen("casa") == (True, "")
        chunks = [e[1] for e in log if e[0] == "chunk"]
        assert max(chunks) <= 3 + 1 + 5 + 3                    # the word, then half a second (and a little lag)
        assert ("leds", 0, 0) not in log                       # still blinking: the house answers next
        v.busy.release()
    asyncio.run(scenario())
