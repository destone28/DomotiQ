# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The conversations of the house.

- **Talk** (held down): the house listens while the button is held, then
  answers the question or runs the command.
- **Intercom**: ding-dong, "Who is it?", and a name. A known name is given
  to the next figurine that comes in through the front door; a new name
  registers a new character.
- **Questions of the house**: when the house is unsure who someone is, it
  asks aloud and on the web app; the next answer settles it. Who a newcomer
  is becomes a short dialogue (who.py) that understands any answer.
- **Small talk** (chatter.py): the welcome of a new phone, and the questions
  and offers of chatty mode, answered without pressing Talk.
- **What the house knows of a character** (facts.py): "cosa mangia
  Rossellina?" is answered with what it was told, or "I don't know".

Only one conversation at a time; pressing Talk while the house speaks
interrupts it.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from ..audio.mic import MIC_RATE, Microphone
from ..identities import NameTaken
from ..model import CATEGORY_NAMES
from ..scenes import scene_name
from . import answers, facts, memory
from .chatter import ECHO_S, NAME_CONFIDENCE, PROPOSALS, QUESTIONS, WELCOME, Chatter, yes_no_grammar, yes_or_no
from .narrator import Narrator
from .stories import StoryTeller
from .intents import (DENY, Intent, find_name, find_room, name_from_speech, normalize, parse, parse_time, said_options,
                      spoken)
from . import variants as V
from .who import BOTH, OR, Dialogue
from .llm import LanguageModel
from .stt import Listener
from .tts import Speaker

if TYPE_CHECKING:
    from ..app import Context

log = logging.getLogger(__name__)

YES = {"it": ["si", "sì", "certo", "esatto", "giusto", "va bene"], "en": ["yes", "yeah", "right", "correct", "sure"]}
NO = {"it": ["no", "sbagliato"], "en": ["no", "wrong", "nope"]}
# what the language model may propose that changes the house (asked first unless it is sure)
ACTIONS = ("lights_on", "lights_off", "scene", "party", "grill", "grill_stop", "language", "volume", "register")
SURE = 0.9
HOLD_MAX_S = 6.0      # the microphone waits at most this long for the house to finish speaking
TAG_DELAY_S = 2.0     # the facts of a character are looked at this long after a change (several come together)
ENTRANCE_S = 180.0    # after the intercom, the first figurine that comes in within this long is the one who rang
CONTEXT_S = 90.0      # a question with no name, this soon after one about a character, is about that character
# the furniture a character may stand on: "Marco è sul divano?" asks where Marco is
PLACE_WORDS = re.compile(r"\b(letto|divano|poltrona|tavolo|tavolino|bancone|frigo\w*|panca|panchina|albero|credenza|"
                         r"comodino|doccia|bed|sofa|couch|armchair|table|counter|fridge|bench|tree|sideboard|shower)\b")
ABOUT_CUE = re.compile(r"\b(cosa fa|che fa|che lavoro|di dove|dove vive|dove abita|quanti anni|come sta|chi e|"
                       r"cosa (gli|le) piace|what does (he|she) do|where is (he|she) from|how old)\b")
# the word of activation (Settings -> Voice): in place of Talk
WAKE_GAP_S = 1.2      # not listened for until this long after the house spoke: its own voice may say it
WAKE_CONFIDENCE = 0.6 # heard alone and less surely than this, it does not wake the house
WAKE_MAX_S = 60.0     # one opening of the microphone while listening for it, then the next one
WAKE_PREROLL_S = 2.0  # the audio kept from before the word is caught: what is said right with it is not lost
WAKE_TAIL_S = 0.3     # the end of the word itself, still being said when it is caught
WAKE_REST_S = 1.5     # after the word, this long with nothing said: the house asks what is needed
WAKE_END_S = 0.9      # a pause this long after what was said with the word: the request has ended
WAKE_REQUEST_S = 10.0 # what is said with the word, at most

FREQUENT = {
    "it": ["Chi è?", "Scusa, non ho capito. Chi sei?", "Vediamo...", "Non ho capito.", "Si balla!",
           "Festa finita!", "Accendo il barbecue!", "Italiano", "Come si chiama?", "In che stanza l'hai messo?"],
    "en": ["Who is it?", "Sorry, I didn't catch that. Who are you?", "Let me see...", "I didn't get that.",
           "Let's dance!", "The party is over!", "Lighting the barbecue!", "English", "What's the name?",
           "Which room did you put it in?"],
}
for _i, _lang in enumerate(("it", "en")):
    FREQUENT[_lang].append(WELCOME[_lang])
    FREQUENT[_lang] += V.fixed_lines(V.THINKING, V.GIVE_UP, V.LATER, V.NOTHING, V.WAITING, V.WHAT_IS_IT,
                                     V.NAME_AGAIN, V.CAR_PARKED, V.WHICH_ONES)[_lang]


class Voice:
    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        self.speaker = Speaker(cache_dir=ctx.paths.var / "voice")
        self.listener = None if ctx.args.no_voice else Listener(ctx.paths.models)
        audio = ctx.audio
        device = audio.device if audio is not None and not audio.dry else None
        # the microphone is on the same USB sound card: it follows the output if that is found later
        self.mic = Microphone(device, follow=(lambda: audio.device if not audio.dry else None) if audio else None)
        self.llm = None if ctx.args.no_llm else LanguageModel()
        self.llm_ok = False
        self.llm_ready = False                 # its instructions are in the cache: a question costs a few seconds
        self._jokes = random.randrange(100)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self.busy = asyncio.Lock()
        self._talk_stop: asyncio.Event | None = None
        self._talk_task: asyncio.Task | None = None
        self._context: tuple[str, float] | None = None   # the last character talked about, and when
        self._wake_stop: asyncio.Event | None = None     # the microphone is open for the word of activation
        self._wake_idle = asyncio.Event()                # ...and closed again
        self._wake_idle.set()
        self.expect_entrance: dict[str, Any] | None = None   # a name waiting for the front door
        self.question: dict[str, Any] | None = None           # a confirmation asked aloud
        self._asking: asyncio.Task | None = None               # asking it and listening for the answer
        self._asking_stop: dict[str, asyncio.Event] = {}       # confirmation -> stop listening (answered)
        self._last_proposal = 0.0
        self.last_chatter = float("-inf")      # monotonic: the last chatty line, comment or question
        self.in_flight = 0                     # sentences being synthesized or played now
        self.voice_end = float("-inf")         # monotonic: when the last one ended
        self.opened_at = 0.0                   # monotonic: when the last listening began to count
        self._tasks: set[asyncio.Task] = set()
        self.fact_topics: dict[str, str] = {}  # normalized fact -> topic told by the model (facts no keyword describes)
        self._tagging: asyncio.Task | None = None
        self._facts_seen: tuple[str, ...] | None = None   # every fact, when the model last looked at them
        bus = ctx.bus
        bus.subscribe("confirm", self._on_confirm)
        bus.subscribe("confirm_closed", self._on_confirm_closed)
        bus.subscribe("room_enter", self._on_room_enter)
        bus.subscribe("track_appear", self._on_track_appear)
        bus.subscribe("registered", self._on_registered)
        bus.subscribe("count_changed", self._on_count)
        bus.subscribe("identities_changed", self._on_identities)
        self.chatter = Chatter(self)
        self.narrator = Narrator(self)
        self.who = Dialogue(self)
        self.stories = StoryTeller(self)
        # a story in one language stops when the house changes language, rather than go on in the old one
        bus.subscribe("language", lambda ev: self._spawn(self.stories.preempt()) if self.stories.active else None)

    # ================================================================ lifecycle
    @property
    def lang(self) -> str:
        return self.ctx.settings.get("voice.language", "it")

    async def start(self) -> None:
        self._spawn(self._background())
        self._spawn(self.narrator.run())

    async def stop(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _background(self) -> None:
        # the language model gets its instructions ready meanwhile: they do not wait for the voice
        self._spawn(self._keep_model())
        self._spawn(self._wake_loop())
        try:
            await self.speaker.warm(FREQUENT)
        except Exception:  # noqa: BLE001
            log.exception("warming the voice failed")
        if self.listener and self.listener.ok:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(self.pool, self.listener.model, self.lang)
            except Exception as e:  # noqa: BLE001
                log.warning("speech model not loaded: %s", e)

    async def _keep_model(self) -> None:
        """Is the language model there? Once it is, its instructions go in the cache (put back from the last start,
        or read), and again if llama-server starts again."""
        if self.llm is None:
            return
        loop = asyncio.get_running_loop()
        while True:
            self.llm_ok = await loop.run_in_executor(None, self.llm.health)
            if not self.llm_ok or getattr(self.llm, "cold", False):
                self.llm_ready = False            # stopped or started again: its cache is empty
            if self.llm_ok and not self.llm_ready:
                # stopped while reading (an update of its service): tried again at the next round
                self.llm_ready = await loop.run_in_executor(None, self.llm.warm)
                if self.llm_ready:
                    self._tag_facts_later()
            await asyncio.sleep(30)

    def status(self) -> dict[str, Any]:
        return {"ok": bool(self.listener and self.listener.ok) or self.speaker.ok,
                "stt": "vosk" if self.listener and self.listener.ok else "",
                "tts": self.speaker.ok, "llm": self.llm_ok, "stories": self.stories.ok, "mic": self.mic.available,
                "level": round(self.mic.last_level, 3)}

    # ================================================================ speaking
    async def speak(self, text: str, lang: str | None = None) -> None:
        lang = lang or self.lang
        self.in_flight += 1
        await self.ctx.actions.thinking(False)             # it knows what to say: the buttons stop breathing
        try:
            samples = await self.speaker.synth(text, lang)
            if samples is None:
                return
            await self._play(samples)
        finally:
            self.in_flight -= 1
            self.voice_end = time.monotonic()

    async def play(self, samples) -> None:
        """Speech already synthesized (the storyteller prepares the next sentence while one plays)."""
        self.in_flight += 1
        try:
            await self._play(samples)
        finally:
            self.in_flight -= 1
            self.voice_end = time.monotonic()

    async def _play(self, samples) -> None:
        await self.ctx.actions.speaking(True)              # the LEDs of the buttons stay on while it speaks
        try:
            if self.ctx.audio is not None and not (self.ctx.sim.enabled and self.ctx.sim.mute):
                await self.ctx.audio.play_voice(samples)
            else:
                await asyncio.sleep(len(samples) / 22050)
        finally:
            await self.ctx.actions.speaking(False)

    async def say(self, text: str, level: str = "normal") -> None:
        await self.ctx.actions.say(text, level=level)

    async def reply(self, text_it: str, text_en: str | None = None) -> None:
        await self.ctx.actions.say({"it": text_it, "en": text_en or text_it})

    async def _beep(self, name: str) -> None:
        if self.ctx.audio is not None:
            await self.ctx.audio.effect(name)

    # ================================================================ listening
    async def _listen(self, grammar: list[str] | None, *, stop: asyncio.Event | None = None,
                      max_s: float = 5.0, auto_end: bool = True, hold: Callable[[], bool] | None = None,
                      echo: float = 0.0) -> tuple[str, float, bytes]:
        """Record and recognize. With `auto_end`, stop after a pause following speech.

        With `hold` (the house is still speaking) the microphone is already open while the house ends its
        question, and what it hears is dropped until `echo` seconds after the last word: an answer said at
        once ("sì") is not lost while the recorder starts. `max_s` counts from then.
        """
        self.opened_at = 0.0
        if not (self.listener and self.listener.ok):
            return "", 0.0, b""
        await self._yield_mic()
        loop = asyncio.get_running_loop()
        lang = self.lang
        session = await loop.run_in_executor(self.pool, self.listener.session, lang, grammar)
        stop = stop or asyncio.Event()
        started = loop.time()
        state = {"speech": False, "quiet": 0.0, "opened": None, "held": started}
        kept = bytearray()
        feeds: list[asyncio.Future] = []

        def on_chunk(chunk: bytes) -> None:
            now = loop.time()
            if state["opened"] is None:
                if hold is not None and now - started < HOLD_MAX_S and hold():
                    state["held"] = now                # the house itself: not an answer
                    return
                if now - state["held"] < echo:
                    return
                state["opened"] = now
                self.opened_at = time.monotonic()
            kept.extend(chunk)
            feeds.append(loop.run_in_executor(self.pool, session.feed, chunk))
            if self.mic.last_level > 0.02:
                state["speech"], state["quiet"] = True, 0.0
            elif state["speech"]:
                state["quiet"] += 0.1
                if auto_end and state["quiet"] >= 0.8:
                    stop.set()
            if now - state["opened"] >= max_s:
                stop.set()

        self.ctx.bus.publish("listening", on=True)
        await self.ctx.actions.update_leds(listening=True)
        try:
            await self.mic.listen(stop, on_chunk, max_s=max_s + (HOLD_MAX_S + echo if hold else echo))
        finally:
            self.ctx.bus.publish("listening", on=False)
            await self.ctx.actions.update_leds()
        audio = bytes(kept)
        if state["speech"]:
            await self.ctx.actions.thinking(True)          # something was said: the house works on it
        if feeds:
            await asyncio.gather(*feeds, return_exceptions=True)
        text, conf = await loop.run_in_executor(self.pool, session.result)
        self.ctx.bus.publish("heard", text=text, confidence=round(conf, 2))
        log.info("heard %r (%.2f)", text, conf)
        return text, conf, audio

    async def _recognize(self, audio: bytes, grammar: list[str] | None) -> tuple[str, float]:
        if not audio or not (self.listener and self.listener.ok):
            return "", 0.0
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(self.pool, self.listener.session, self.lang, grammar)
        await loop.run_in_executor(self.pool, session.feed, audio)
        return await loop.run_in_executor(self.pool, session.result)

    def _names(self) -> list[str]:
        out = []
        for i in self.ctx.identities.all():
            out.append(i.name)
            if i.alias_en:
                out.append(i.alias_en)
        return out

    # ================================================================ word of activation
    def wake_phrase(self) -> str:
        """The word of activation as the speech recognizer writes it ("Casa 2" is "casa due"); "" when it is off."""
        s = self.ctx.settings
        if not s.get("voice.wake_enabled", False):
            return ""
        return spoken(s.get("voice.wake_word", "") or "", self.lang)

    def wake_check(self, word: str) -> dict[str, Any]:
        """How the speech recognizer would hear this word of activation, and its words it does not know."""
        phrase = spoken(word, self.lang)
        unknown = [] if not (self.listener and self.listener.ok) else \
            [w for w in phrase.split() if not self.listener.known(w, self.lang)]
        return {"spoken": phrase, "unknown": unknown}

    def _wake_free(self) -> bool:
        """Nothing else needs the house or the microphone: the word of activation can be listened for."""
        return (not self.busy.locked() and not self.in_flight and self.question is None and not self.chatter.asking
                and (self._talk_task is None or self._talk_task.done())
                and time.monotonic() - self.voice_end >= WAKE_GAP_S and self.ctx.actions.speaks("normal"))

    async def _yield_mic(self) -> None:
        """Somebody else needs the microphone: the listening for the word of activation gives it back."""
        stop = self._wake_stop
        if stop is None:
            return
        stop.set()
        try:
            await asyncio.wait_for(self._wake_idle.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass

    async def _wake_loop(self) -> None:
        """With the word of activation on, the microphone listens for it whenever the house is free; the word does
        what Talk does. The audio is never kept."""
        while True:
            phrase = self.wake_phrase()
            if not phrase or not (self.listener and self.listener.ok) or not self.mic.available \
                    or not self._wake_free():
                await asyncio.sleep(0.3)
                continue
            try:
                woke, rest = await self._wake_listen(phrase)
            except Exception:  # noqa: BLE001
                log.exception("listening for the word of activation failed")
                await asyncio.sleep(5.0)
                continue
            if woke:
                await self._woken(rest, held=True)
            else:
                await asyncio.sleep(0.05)

    async def _wake_listen(self, phrase: str) -> tuple[bool, str]:
        """The microphone open for a long stretch, the speech recognizer held to the word: its partial result tells
        the word while it is still being said, and at that moment the house takes the turn and the LEDs blink. The
        free recognizer starts on the last seconds of audio and goes on with what follows, until a pause: what was
        said right with the word ("Casa, accendi la luce in cucina") is the request, ready when it ends.

        Returns whether the word was said (then the house is held: `busy`, for `_woken`) and the request. Ends with
        nothing when something else needs the house or the microphone, and when the free recognizer did not hear
        the word in what was said (talk near the house)."""
        loop = asyncio.get_running_loop()
        lang = self.lang
        spot = await loop.run_in_executor(self.pool, self.listener.session, lang, [phrase])
        stop = asyncio.Event()
        chunks: asyncio.Queue = asyncio.Queue()

        def on_chunk(chunk: bytes) -> None:
            chunks.put_nowait((chunk, self.mic.last_level))

        ring: deque[bytes] = deque(maxlen=round(WAKE_PREROLL_S * 10))      # chunks of 100 ms
        held, free, sure = False, None, 0.0
        feeds: list[asyncio.Future] = []
        after = quiet = 0.0
        speech = False
        self._wake_stop = stop
        self._wake_idle.clear()
        mic = asyncio.ensure_future(self.mic.listen(stop, on_chunk, max_s=WAKE_MAX_S))
        try:
            while True:
                try:
                    chunk, level = chunks.get_nowait()
                except asyncio.QueueEmpty:
                    if mic.done():
                        break                               # the microphone closed
                    getter = asyncio.ensure_future(chunks.get())
                    await asyncio.wait({getter, mic}, return_when=asyncio.FIRST_COMPLETED)
                    if not getter.done():
                        getter.cancel()
                        continue
                    chunk, level = getter.result()
                if not held:
                    if not self._wake_free():
                        break                               # Talk, a question, the house speaking: it comes first
                    ring.append(chunk)
                    heard = await loop.run_in_executor(self.pool, spot.feed_partial, chunk)
                    if f" {phrase} " not in f" {spoken(heard, lang)} ":
                        continue
                    if self.busy.locked():
                        break
                    await self.busy.acquire()
                    held = True
                    # caught: the house shows at once that it listens, and nothing else starts talking
                    self.ctx.bus.publish("listening", on=True)
                    await self.ctx.actions.update_leds(listening=True)
                    sure = await loop.run_in_executor(self.pool, spot.sureness, phrase)
                    free = await loop.run_in_executor(self.pool, self.listener.session, lang, None)
                    feeds.append(loop.run_in_executor(self.pool, free.feed, b"".join(ring)))
                    continue
                feeds.append(loop.run_in_executor(self.pool, free.feed, chunk))
                after += 0.1
                if level > 0.02 and after > WAKE_TAIL_S:
                    speech, quiet = True, 0.0
                else:
                    quiet += 0.1
                if (speech and quiet >= WAKE_END_S) or (not speech and after >= WAKE_REST_S) \
                        or after >= WAKE_REQUEST_S:
                    break
        except BaseException:
            if held:
                self.busy.release()
            raise
        finally:
            stop.set()
            await asyncio.gather(mic, return_exceptions=True)
            self._wake_stop = None
            self._wake_idle.set()
        if not held:
            return False, ""
        try:
            self.ctx.bus.publish("listening", on=False)
            await self.ctx.actions.update_leds()
            await asyncio.gather(*feeds, return_exceptions=True)
            text, _ = await loop.run_in_executor(self.pool, free.result)
        except BaseException:
            self.busy.release()
            raise
        words, want = spoken(text, lang).split(), phrase.split()
        at = [i for i in range(len(words) - len(want) + 1) if words[i:i + len(want)] == want]
        if at:
            rest = words[at[-1] + len(want):]
        elif len(words) <= 1 and sure >= WAKE_CONFIDENCE:
            rest = []                                       # the word alone, heard a little differently
        else:
            self.busy.release()                             # not the word: talk near the house
            log.info("not the word of activation: %r", text)
            return False, ""
        log.info("word of activation, then %r", " ".join(rest))
        if rest:
            await self.ctx.actions.thinking(True)
        return True, " ".join(rest)

    async def _woken(self, rest: str, held: bool = False) -> None:
        """The word of activation was said: what Talk does. What came right after it is the request; otherwise the
        house asks what is needed, and listens. `held`: the house is already taken (`busy`) for this."""
        log.info("word of activation")
        try:
            if self.ctx.audio is not None:
                self.ctx.audio.stop_voice()
            await self.chatter.preempt()
            await self.stories.preempt()
            await self._preempt_asking()
            if not held:
                if self.busy.locked():
                    return
                await self.busy.acquire()
                held = True
            words = rest.split()
            # one word alone after it is a request only if it means something ("Casa, aiuto!"), not a noise
            text = rest if len(words) >= 2 or (words and parse(rest, self._names()) is not None) else ""
            if not text:
                await self.reply("Dimmi, di cosa hai bisogno?", "Yes? What do you need?")
                text, _, audio = await self._listen(None, max_s=8.0, auto_end=True, hold=self.chatter._speaking,
                                                    echo=ECHO_S)
                if not text:
                    if audio and len(audio) > MIC_RATE:
                        await self.say(answers.not_understood(self.lang))
                    return
            await self.handle(text)
        finally:
            if held:
                self.busy.release()
            await self.ctx.actions.thinking(False)

    # ================================================================ talk button
    async def talk_button(self, pressed: bool) -> None:
        if pressed:
            if self._talk_task and not self._talk_task.done():
                if not self.stories.active:
                    return
                self._talk_task.cancel()              # Talk during a story: the story stops, Talk listens
                await asyncio.wait({self._talk_task}, timeout=2.0)
            if self.ctx.audio is not None:
                self.ctx.audio.stop_voice()
            await self.chatter.preempt()              # Talk comes before the small talk
            await self.stories.preempt()
            await self._preempt_asking()              # the question stays open: Talk can answer it
            self._talk_stop = asyncio.Event()
            self._talk_task = self._spawn(self._talk(self._talk_stop))
        elif self._talk_stop is not None:
            self._talk_stop.set()

    async def _talk(self, stop: asyncio.Event) -> None:
        if self.busy.locked() and self.question is None:
            return
        async with self.busy:
            try:
                await self._beep("beep_start")
                grammar = None
                if self.question:
                    grammar = self._question_grammar()
                text, conf, audio = await self._listen(grammar, stop=stop, max_s=120, auto_end=False)
                await self._beep("beep_end")
                if self.question and not text and audio:
                    text, conf = await self._recognize(audio, None)
                if not text:
                    if audio and len(audio) > MIC_RATE:      # spoke for more than half a second
                        await self.say(answers.not_understood(self.lang))
                    return
                await self.handle(text)
            finally:
                await self.ctx.actions.thinking(False)

    # ================================================================ understanding
    async def handle(self, text: str) -> None:
        lang = self.lang
        names = self._names()
        if self.question and await self._answer_question(text):
            return
        if await self.chatter.answer_by_talk(text):
            return                                    # "sì" to the offer the house has just made
        intent = parse(text, names)
        intent = self._in_context(text, intent, names)
        if intent is None and self.stories.knows(text):
            intent = Intent("other", {}, 0.8, "rules")      # bills, insurance, chores...: the life of the house
        filler = None
        if (intent is None or self._name_alone(intent, text)) and not self._about_a_place(text) \
                and not facts.is_request(text, names):
            # "Marco cura i malati?": about a character the house was told something of, with no keyword: the
            # answer comes at once from what it was told (or "non lo so"), never from the slow language model
            ident = self._told_about(text, names)
            if ident is not None:
                intent = Intent("ask_fact", {"name": ident.name, "topic": facts.question_topic(text, names)}, 0.6,
                                "rules")
        if intent is None and self._about_a_place(text):
            from .intents import find_names
            named = find_names(normalize(text), names)
            if named:
                intent = Intent("where_is", {"name": named[0]}, 0.7, "rules")   # "Marco è sul divano?"
        if intent is None and self.llm is not None:
            filler = filler or asyncio.create_task(self._filler("Vediamo..." if lang == "it" else "Let me see..."))
            intent = await self.llm.understand(text, names)
        if filler is not None:
            await filler
        if intent is not None and intent.source == "llm" and intent.name in ACTIONS and intent.confidence < SURE:
            # the small model may misunderstand: questions are answered at once (at worst the right
            # answer to another question), actions are asked first unless it was quite sure
            it, en = self._describe(intent)
            if not await self._yes_no(it, en):
                await self.reply("D'accordo, niente.", "All right, nothing then.")
                return
        if intent is None and len(text.split()) >= 3:
            intent = Intent("other", {}, 0.5, "rules")      # not a command: a free question about the house
        if intent is None:
            await self.say(answers.not_understood(lang))
            return
        log.info("intent %s %s (%s)", intent.name, intent.args, intent.source)
        intent.args.setdefault("text", text)
        if intent.args.get("name") or intent.args.get("names"):
            self._context = (intent.args.get("name") or intent.args["names"][0], time.monotonic())
        await self.execute(intent)

    async def ask_time(self) -> None:
        """The house does not know the time: it asks, and listens for the answer at once."""
        if self.busy.locked() or self.ctx.clock.known:
            return
        async with self.busy:
            await self.reply("Non so che ore sono: che ore sono adesso?", "I don't know the time: what time is it now?")
            await self._hear_time()

    async def _hear_time(self) -> bool:
        if not (self.listener and self.listener.ok and self.mic.available):
            return False
        for attempt in range(2):
            text, _, _, spoke = await self.chatter._listen(None, max_s=6.0)
            if spoke or not text:
                return False
            hm = parse_time(text)
            if hm and self.ctx.clock.set_hm(hm[0], hm[1], "voice"):
                self.ctx.bus.publish("clock", **self.ctx.clock.to_dict())
                it = "è l'una" if hm[0] == 1 else f"sono le {hm[0]}"
                it += f" e {hm[1]}" if hm[1] else ""
                await self.reply(f"Grazie! Allora {it}.", f"Thanks! So it's {hm[0]}:{hm[1]:02d}.")
                return True
            if attempt == 0:
                await self.reply("Non ho capito l'ora: per esempio, sono le tre e mezza.",
                                 "I didn't get the time: for example, it's half past three.")
        return False

    async def _filler(self, text: str) -> None:
        """A word while the language model thinks, then the buttons breathe until the answer."""
        await self.say(text)
        await self.ctx.actions.thinking(True)

    def _describe(self, intent: Intent) -> tuple[str, str]:
        """The action as a yes/no question, in both languages."""
        a, ctx = intent.args, self.ctx
        room = a.get("room")
        where_it = answers.room(ctx, room, "it") if room else "in tutta la casa"
        where_en = answers.room(ctx, room, "en") if room else "in the whole house"
        n = intent.name
        if n == "lights_on":
            return f"Accendo la luce {where_it}?", f"Shall I turn on the light {where_en}?"
        if n == "lights_off":
            return f"Spengo la luce {where_it}?", f"Shall I turn off the light {where_en}?"
        if n == "scene":
            sc = a.get("scene", "normal")
            return f"Metto lo scenario {scene_name(sc, 'it')}?", f"Shall I switch to the {scene_name(sc, 'en')} scene?"
        if n == "party":
            return "Facciamo festa?", "Shall we party?"
        if n == "grill":
            return "Accendo il barbecue?", "Shall I light the barbecue?"
        if n == "grill_stop":
            return "Spengo il barbecue?", "Shall I turn off the barbecue?"
        if n == "language":
            return ("Passo all'inglese?", "Shall I speak English?") if a.get("language") == "en" \
                else ("Passo all'italiano?", "Shall I speak Italian?")
        if n == "volume":
            return ("Alzo il volume?", "Louder?") if a.get("direction") == "up" else ("Abbasso il volume?", "Quieter?")
        return "Vuoi registrare un personaggio nuovo?", "Do you want to add a new character?"

    async def execute(self, intent: Intent) -> None:
        ctx, lang, a = self.ctx, self.lang, intent.args
        name = intent.name
        act = ctx.actions
        if name == "where_is":
            await self.say(answers.where_is(ctx, a.get("name", ""), lang))
        elif name == "who_in":
            await self.say(answers.who_in(ctx, a.get("room"), lang))
        elif name == "count":
            await self.say(answers.count(ctx, a.get("room"), a.get("what", "persons"), lang))
        elif name == "temperature":
            await self.say(answers.temperature(ctx, a.get("room"), lang))
        elif name == "humidity":
            await self.say(answers.humidity(ctx, a.get("room"), lang))
        elif name == "time_now":
            await self.say(answers.time_now(ctx, lang))
            if not ctx.clock.known:
                await self._hear_time()               # the answer comes with no need to press Talk
        elif name == "set_time":
            ok = ctx.clock.set_hm(int(a["hour"]), int(a["minute"]), "voice")
            ctx.bus.publish("clock", **ctx.clock.to_dict())
            if ok:
                it = f"sono le {a['hour']}" + (f" e {a['minute']}" if a["minute"] else "")
                if a["hour"] == 1:
                    it = "è l'una" + (f" e {a['minute']}" if a["minute"] else "")
                await self.reply(f"D'accordo, {it}.", f"All right, it's {a['hour']}:{a['minute']:02d}.")
        elif name == "lights_on":
            room = a.get("room", "all")
            if room != "all" and ctx.layout.light_of_room(room) is None:
                where_it, where_en = answers.room(ctx, room, "it"), answers.room(ctx, room, "en")
                await self.reply(f"{where_it[0].upper()}{where_it[1:]} non ci sono luci.",
                                 f"There are no lights {where_en}.")
                return
            await act.light(room, a.get("color", "warm"), "solid", int(a.get("brightness", 60)))
            if not a.get("quiet"):                    # quiet: the house has just said what it does
                await self.reply("Fatto.", "Done.")
        elif name == "lights_fav":
            await self._favourite_light(a.get("name", ""), a.get("room"))
        elif name == "together":
            await self._together(a.get("names") or [], a.get("room"))
        elif name == "lights_off":
            await act.lights_off(a.get("room", "all"))
            if not a.get("quiet"):
                await self.reply("Spento.", "Off.")
        elif name == "scene":
            greeting = a.get("greeting")
            await act.scene(a.get("scene", "normal"), announce=not greeting and not a.get("quiet"))
            if greeting == "night":
                await self.reply("Buonanotte! Spengo tutto, sogni d'oro.", "Good night! Lights off, sweet dreams.")
            elif greeting == "morning":
                await self.reply("Buongiorno! Una bella giornata ci aspetta.", "Good morning! A lovely day ahead.")
        elif name == "party":
            if not await act.party():
                await self.reply("Un attimo di pausa, poi rifacciamo festa!", "Give me a moment, then we party again!")
        elif name == "grill":
            if not await act.grill():
                await self.reply("Il barbecue è già acceso, o si sta raffreddando.", "The barbecue is already on, or cooling down.")
        elif name == "grill_stop":
            await act.grill_stop()
            await self.reply("Barbecue spento.", "Barbecue off.")
        elif name == "car_where":
            await self.say(answers.car_where(ctx, lang))
        elif name == "house_summary":
            await self.say(answers.summary(ctx, lang))
        elif name == "help":
            await self.say(answers.help_text(lang))
        elif name == "who_are_you":
            await self.say(answers.who_are_you(lang))
        elif name == "language":
            await act.set_language(a.get("language", "it"))
        elif name == "verbosity":
            await act.set_verbosity(a.get("level", "normal"))
            await self.reply({"silent": "Va bene, sto zitta.", "chatty": "Evviva, adesso parlo di più!",
                              "normal": "D'accordo."}[a.get("level", "normal")],
                             {"silent": "OK, I'll be quiet.", "chatty": "Great, I'll talk more!",
                              "normal": "All right."}[a.get("level", "normal")])
        elif name == "volume":
            v = int(ctx.settings.get("voice.volume", 70)) + (15 if a.get("direction") == "up" else -15)
            await act.set_volume(v)
            await self.reply("Così va meglio?", "Is this better?")
        elif name == "register":
            await self.register_by_voice()
        elif name == "joke":
            self._jokes += 1
            await self.say(answers.joke(lang, self._jokes))
        elif name in ("yes", "no", "cancel"):
            await self.reply("D'accordo.", "OK.")
        elif name == "fact":
            await self._learn_fact(a.get("name", ""), a.get("text", ""))
        elif name == "ask_fact":
            await self._ask_fact(a.get("name", ""), a.get("text", ""), a.get("topic"), asked=intent.source == "llm")
        elif name == "remember":
            what = a.get("what")
            if what == "day":
                await self.say(memory.day_of(ctx, a.get("name", ""), lang))
            elif what == "room":
                await self.say(memory.room_day(ctx, a.get("room"), lang))
            else:
                await self.say(memory.parties_today(ctx, lang))
        elif name == "about":
            await self.stories.tell_about(a.get("name", ""))
        elif name == "story":
            await self.stories.tell(a.get("names"), a.get("room"), bool(a.get("party")))
        elif name in ("recall", "other"):
            await self.stories.answer(a.get("text", ""), a.get("names") or self._mentioned(a.get("text", "")),
                                      memory=name == "recall")
        else:
            await self.say(answers.off_topic(lang))

    def _mentioned(self, text: str) -> list[str]:
        from .intents import find_names
        return find_names(normalize(text), self._names())

    def _in_context(self, text: str, intent: Intent | None, names: list[str]) -> Intent | None:
        """"Che lavoro fa?" right after a question about Rossellina is about Rossellina: a question about a character
        with no name in it goes to the last character talked about, for CONTEXT_S."""
        if self._context is None or time.monotonic() - self._context[1] > CONTEXT_S:
            return intent
        if intent is not None and intent.name not in ("other", "house_summary", "help", "who_are_you"):
            return intent
        from .intents import find_names
        t = normalize(text)
        if find_names(t, names) or not (facts.question_topic(text, names) or ABOUT_CUE.search(t)):
            return intent
        return parse(f"{text} {self._context[0]}", names) or intent

    def _name_alone(self, intent: Intent, text: str) -> bool:
        """The rules took a short sentence with a name for "where is" ("Marco è medico?"), not "dov'è Marco"."""
        return (intent.name == "where_is" and intent.source == "rules" and intent.confidence < 0.8
                and len(normalize(text).split()) > len(normalize(intent.args.get("name", "")).split()))

    @staticmethod
    def _about_a_place(text: str) -> bool:
        """"Dove Marco?", "Marco è in cucina?", "Marco è sul divano?": where somebody is, which the commands answer
        without delay."""
        t = normalize(text)
        return bool(find_room(t) or re.search(r"\b(dove|dov|where|stanza|room)\b", t) or PLACE_WORDS.search(t))

    def _told_about(self, text: str, names: list[str]):
        """The first character named in the sentence, if the house was told something about it."""
        from .intents import find_names
        for n in find_names(normalize(text), names):
            ident = self.ctx.identities.by_name(n)
            if ident is not None:
                return ident if ident.facts else None
        return None

    async def _together(self, names: list[str], room: str | None) -> None:
        """"Mister Brown e Rossellina stanno insieme": two figurines touching are one blob. The presence of one of them
        (in the room said, if any) is both, the other hidden behind it until a hand parts them; with neither seen,
        the one presence the house does not know yet."""
        ctx = self.ctx
        idents = [i for i in (ctx.identities.by_name(n) for n in names) if i is not None]
        if len(idents) == 1:
            await self.reply(f"Ho capito solo {idents[0].name}: dimmi di nuovo chi c'è insieme.",
                             f"I only caught {idents[0].name}: tell me again who is with them.")
            return
        if len(idents) < 2:
            await self.reply("Non conosco tutti e due.", "I don't know both of them.")
            return
        ids = {i.id for i in idents}
        seen = [t for t in ctx.house.tracks.values() if not t.carried and (room is None or t.room == room)]
        target = next((t for t in seen if t.identity in ids), None)
        if target is None:
            loose = [t for t in seen if not t.identity or t.uncertain]
            target = loose[0] if len(loose) == 1 else None
        if target is None:
            await self.reply("Non li vedo: mettili dove la webcam li vede, oppure dimmi in che stanza sono.",
                             "I can't see them: put them where the camera sees them, or tell me the room.")
            return
        if target.virtual:
            obj = ctx.sim.objects.get(target.id)
            if obj is not None and obj.identity not in ids:
                obj.identity, obj.name = idents[0].id, idents[0].name
        else:
            ctx.vision.together(target.id, [i.id for i in idents])
        where = target.room
        await self.reply(*V.said_each(
            "who.together", V.TOGETHER,
            {"names": answers.join([i.name for i in idents], "it"), "where": answers.room(ctx, where, "it") if where else "lì"},
            {"names": answers.join([i.name for i in idents], "en"), "where": answers.room(ctx, where, "en") if where else "there"}))

    async def _favourite_light(self, name: str, room: str | None) -> None:
        """"Accendi la luce preferita di Marco": the room said, or the one Marco is in, in the colour Marco told the
        house. Not told yet: the house asks Marco now, if Marco is in the house."""
        ctx = self.ctx
        ident = ctx.identities.by_name(name)
        if ident is None:
            await self.reply(f"Non conosco nessuno che si chiama {name}.", f"I don't know anyone called {name}.")
            return
        colour = facts.favourite_colour(ident.facts)
        here = ctx.house.where_is(ident.id)
        where = room or (here.room if here is not None else None)
        if colour is None:
            if here is not None and ctx.layout.light_of_room(here.room) is not None:
                await self.reply(f"Non lo so ancora: lo chiedo a {ident.name}.", f"I don't know yet: I'll ask {ident.name}.")
                q = next(q for q in QUESTIONS if q["id"] == "a-colour")
                self.chatter.asking = True
                self._spawn(self.chatter._ask(ident.id, q, forced=True))      # its answer lights the room
            else:
                await self.reply(f"Non so ancora il colore preferito di {ident.name}: chiediglielo con Fai domande.",
                                 f"I don't know {ident.name}'s favourite colour yet: ask with Ask questions.")
            return
        if where is None:
            await self.reply(f"{ident.name} non è in casa: dimmi anche la stanza.",
                             f"{ident.name} is not in the house: tell me the room too.")
            return
        await self.execute(Intent("lights_on", {"room": where, "color": colour, "brightness": 70}, 1.0, "rules"))

    async def _ask_fact(self, name: str, text: str, topic: str | None, asked: bool = False) -> None:
        """"Cosa mangia Rossellina?": what the house was told about it, else the life of the house, else that it
        does not know."""
        ident = self.ctx.identities.by_name(name)
        if ident is None:
            await self.reply(f"Non conosco nessuno che si chiama {name}.", f"I don't know anyone called {name}.")
            return
        names = self._names()
        # by its keywords, then by the words it shares with a fact: at once, never waiting for the language model
        chosen = facts.select(topic, ident.facts, self.fact_topics, names=names) if topic else []
        if not chosen:
            chosen = facts.overlap(text, ident.facts, names)
        if not chosen and topic == facts.LIKES:
            chosen = facts.select(facts.LIKES, ident.facts, self.fact_topics, names=names)
        if chosen:
            await self.stories.tell_facts(ident, chosen)
        elif self.stories.knows(text):
            await self.stories.answer(text, [ident.name])     # "dove va in vacanza Luca?": made up, then kept
        else:
            it, en = V.said("facts-unknown", facts.UNKNOWN, name=ident.name)
            await self.reply(it, en)

    def _on_identities(self, ev) -> None:
        if ev.get("action") != "delete":
            self._tag_facts_later()

    def _all_facts(self) -> tuple[str, ...]:
        return tuple(f for i in self.ctx.identities.all() for f in i.facts)

    def _tag_facts_later(self) -> None:
        if self.llm is None or not self.llm_ready or (self._tagging is not None and not self._tagging.done()):
            return
        if self._all_facts() == self._facts_seen:
            return                                    # most changes are the vision learning a colour or a pose
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return                                    # not started yet: the start looks at the facts anyway
        self._tagging = self._spawn(self._tag_facts())

    async def _tag_facts(self) -> None:
        """The topic of the facts no keyword describes ("ha un debole per i fumetti"), asked to the model while
        the house is free, so that a question finds them too; the facts already known are skipped."""
        await asyncio.sleep(TAG_DELAY_S)
        while True:
            told, names = self._all_facts(), self._names()
            for f in told:
                key = normalize(f)
                if key in self.fact_topics or not facts.needs_model(f, names):
                    continue
                while self.busy.locked():
                    await asyncio.sleep(1.0)          # a conversation comes first
                topic = await self.llm.topic(f, least=facts.TAG_CONFIDENCE)
                if topic is None:
                    return                            # the model is not there: the next change tries again
                self.fact_topics[key] = topic
            self._facts_seen = told
            if self._all_facts() == told:             # nothing changed meanwhile
                return

    async def _learn_fact(self, name: str, text: str) -> None:
        """"Ricorda che Marco fa il medico": "fa il medico" joins what the house knows about Marco."""
        ident = self.ctx.identities.by_name(name)
        if not ident:
            await self.reply(f"Non conosco nessuno che si chiama {name}.", f"I don't know anyone called {name}.")
            return
        fact = re.sub(r"^\s*(ricorda(ti|te)?|memorizza|segnati|remember|note|keep in mind)\s+(che|that)\s+", "",
                      text.strip(), flags=re.I).strip(" .")
        for alias in filter(None, (ident.name, ident.alias_en)):
            if normalize(fact).startswith(normalize(alias) + " "):
                fact = fact[len(alias):].strip()
                break
        if len(fact.split()) < 2:
            await self.reply("Cosa devo ricordare?", "What should I remember?")
            return
        self.ctx.identities.add_fact(ident.id, fact)
        await self.reply(f"Me lo ricorderò: {ident.name} {fact}.", f"I'll remember: {ident.name} {fact}.")

    # ================================================================ intercom
    async def intercom(self) -> None:
        await self.chatter.preempt()                  # the doorbell comes before the small talk
        if self.busy.locked():
            return
        self._spawn(self._intercom())

    async def _intercom(self) -> None:
        ctx, lang = self.ctx, self.lang
        async with self.busy:
            await ctx.actions.update_leds(waiting=True)
            try:
                if ctx.audio is not None:
                    await ctx.audio.effect_wait("bell")
                ctx.bus.publish("doorbell")
                ctx.store.add_event("doorbell", {})
                await self.reply("Chi è?", "Who is it?")
                name = await self._ask_name(allow_new=True)
                if not name:
                    await self.reply("Non ti conosco, ma entra pure: sei un ospite.",
                                     "I don't know you, but come in: you're a guest.")
                    return
                ident = ctx.identities.by_name(name)
                if ident:
                    inside = ctx.house.where_is(ident.id)
                    if inside and inside.room not in ("driveway", "outside"):
                        where = answers.room(ctx, inside.room, lang)
                        await self.reply(f"Ma {ident.name} è già {where}!", f"But {ident.name} is already {where}!")
                        return
                    self.expect_entrance = {"identity": ident.id, "name": ident.name,
                                            "until": time.time() + ENTRANCE_S}
                    await self.reply(f"Ciao {ident.name}, entra pure!", f"Hi {ident.name}, come on in!")
                else:
                    await self._register_named(name, origin="intercom")
            finally:
                await ctx.actions.update_leds()

    async def _ask_name(self, allow_new: bool) -> str | None:
        """Listen for a name; a known one through the grammar, a new one from free speech."""
        names = self._names()
        for attempt in range(2):
            text, conf, audio = await self._listen(names + YES[self.lang] if names else None, max_s=5.0,
                                                   hold=self.chatter._speaking, echo=ECHO_S)
            known = find_name(normalize(text), names, 0.8) if text else None
            if known:
                return known
            if allow_new and audio:
                free, _ = await self._recognize(audio, None)
                candidate = name_from_speech(free)
                if candidate:
                    if await self._yes_no(f"Ho capito {candidate}, giusto?", f"I heard {candidate}, right?"):
                        return candidate
            if attempt == 0:
                await self.reply("Scusa, non ho capito. Chi sei?", "Sorry, I didn't catch that. Who are you?")
        return None

    async def _yes_no(self, it: str, en: str) -> bool:
        await self.reply(it, en)
        text, _, _ = await self._listen(YES[self.lang] + NO[self.lang], max_s=4.0, hold=self.chatter._speaking,
                                        echo=ECHO_S)
        t = normalize(text)
        return any(t.startswith(normalize(y)) for y in YES[self.lang])

    async def _register_named(self, name: str, origin: str, room: str | None = None) -> None:
        ctx = self.ctx
        if ctx.identities.by_name(name):
            await self.reply(f"C'è già qualcuno che si chiama {name}: aggiungi un soprannome dalla webapp.",
                             f"Someone is already called {name}: add a nickname from the web app.")
            return
        if origin == "intercom":
            # whoever comes into the house in the next minutes is the new one
            self.expect_entrance = {"new": name, "until": time.time() + ENTRANCE_S}
            await self.reply(f"Piacere, {name}! Entra dalla porta.", f"Nice to meet you, {name}! Come in through the door.")
            return
        try:
            s = ctx.registration.start(name, origin=origin, room=room, auto=True)
        except NameTaken:
            return
        where_it = answers.room(ctx, room, "it") if room else "in casa"
        where_en = answers.room(ctx, room, "en") if room else "in the house"
        if s.status == "choose":
            await self.reply(f"Vedo più di un personaggio nuovo {where_it}: scegli {name} dalla webapp.",
                             f"I see more than one newcomer {where_en}: pick {name} in the web app.")
        elif s.status == "waiting":
            await self.reply(f"Va bene: mettilo {where_it}, lo aspetto.", f"OK: put it {where_en}, I'm waiting.")

    async def register_by_voice(self) -> None:
        await self.reply("Come si chiama?", "What's the name?")
        name = await self._ask_name(allow_new=True)
        if not name:
            await self.reply("Lasciamo stare, riprova dalla webapp.", "Let's leave it, try from the web app.")
            return
        if self.ctx.identities.by_name(name):
            await self.reply(f"Conosco già {name}.", f"I already know {name}.")
            return
        await self.reply("In che stanza l'hai messo?", "Which room did you put it in?")
        rooms = ["cucina", "soggiorno", "camera", "bagno", "garage", "giardino", "vialetto", "tecnico"] \
            if self.lang == "it" else ["kitchen", "living room", "bedroom", "bathroom", "garage", "garden", "driveway", "utility room"]
        text, _, _ = await self._listen(rooms, max_s=4.0, hold=self.chatter._speaking, echo=ECHO_S)
        room = find_room(normalize(text))
        await self._register_named(name, origin="voice", room=room)

    def _on_registered(self, ev) -> None:
        if ev.get("origin") in ("intercom", "voice"):
            cat = CATEGORY_NAMES.get(ev.get("category"), {})
            self._spawn(self.reply(f"Benvenuto, {ev.get('name')}! Ora ti riconosco.",
                                   f"Welcome, {ev.get('name')}! Now I know you."))
            _ = cat

    # ================================================================ front door
    def _on_track_appear(self, ev) -> None:
        self._maybe_assign(ev, "track_appear")

    def _on_room_enter(self, ev) -> None:
        self._maybe_assign(ev, "room_enter")

    def _maybe_assign(self, ev, kind: str) -> None:
        """After the intercom, the first figurine that appears in the house (or on the driveway, on its way to the
        door) is the one who rang: whatever the webcam took it for (a figurine is often an "object" for it), unless
        the house recognized someone else for sure. A character already in the house before does not count."""
        exp = self.expect_entrance
        if not exp or time.time() > exp["until"]:
            self.expect_entrance = None
            return
        if kind == "track_appear":
            exp.setdefault("came", set()).add(ev.get("track"))        # appeared after the bell rang
        if ev.get("track") not in exp.get("came", ()) or ev.get("room") in (None, "garage", "outside"):
            return
        track = self.ctx.house.tracks.get(ev.get("track"))
        if track is None and kind == "track_appear":
            # told while the house is still taking in the new tracks: looked at as soon as it has done
            try:
                asyncio.get_running_loop().call_soon(self._maybe_assign, ev, "appeared")
            except RuntimeError:
                pass
            return
        if not track or track.carried or track.category == "car":
            return
        sure = track.identity and not track.uncertain
        if "new" in exp:
            if sure:
                return            # somebody the house knows, not the new one
            self.expect_entrance = None
            try:
                self.ctx.registration.start(exp["new"], origin="intercom", room=track.room, category="person",
                                            track=track.id, auto=True, force=True)
            except (NameTaken, ValueError):
                pass
            return
        if sure and track.identity != exp["identity"]:
            seen = self.ctx.identities.name_of(track.identity)
            self._spawn(self.reply(f"Mmm, a me sembri {seen}, non {exp['name']}!",
                                   f"Hmm, you look like {seen} to me, not {exp['name']}!"))
            self.expect_entrance = None
            return
        if track.virtual:
            obj = self.ctx.sim.objects.get(track.id)
            if obj:
                obj.identity, obj.name = exp["identity"], exp["name"]
        else:
            self.ctx.vision.assign(track.id, exp["identity"])
        self.ctx.house.name(track, exp["identity"])
        self.expect_entrance = None
        self.ctx.bus.publish("identity_changed", track=track.id, identity=exp["identity"], name=exp["name"])

    # ================================================================ questions of the house
    def _on_confirm(self, ev) -> None:
        self.question = {"id": ev.get("id"), "options": ev.get("options") or [],
                         "allow_name": bool(ev.get("allow_name"))}
        self._asking = self._spawn(self._ask_aloud(dict(ev.data)))

    def _on_confirm_closed(self, ev) -> None:
        stop = self._asking_stop.pop(ev.get("id"), None)
        if stop is not None:
            stop.set()                                # answered on a phone: no need to listen any more
        if self.question and self.question["id"] == ev.get("id"):
            self.question = None

    async def _preempt_asking(self) -> None:
        task = self._asking
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            await asyncio.wait({task}, timeout=2.0)

    async def _ask_aloud(self, ev: dict[str, Any]) -> None:
        """Say a question of the house and wait for the answer aloud, with no need to press Talk; a phone may
        answer meanwhile, and the first answer wins."""
        cid = ev.get("id")
        house = self.ctx.house
        stop = self._asking_stop.setdefault(cid, asyncio.Event())
        try:
            await self.chatter.preempt()
            async with self.busy:
                if cid not in house.confirmations:
                    return
                await self.ctx.actions.say(ev.get("question") or {})
                if not self.ctx.actions.speaks("normal") or not (self.listener and self.listener.ok) \
                        or not self.mic.available:
                    return                            # silent mode or no microphone: the phones answer
                if (ev.get("context") or {}).get("kind") == "who" and ev.get("allow_name"):
                    await self.who.run(ev, stop)      # a newcomer: a dialogue that understands any answer
                    return
                labels = [((o.get("label") or {}).get(self.lang) or "") for o in ev.get("options") or []]
                grammar = [w for w in labels if w] + yes_no_grammar(self.lang)
                if len([w for w in labels if w]) >= 2:
                    # "tutti e due", "sia Viola che Rosaria": all of them are there
                    grammar += BOTH[self.lang] + (["e", "sia", "che"] if self.lang == "it" else ["and"])
                for attempt in range(2):
                    text, conf, _, spoke = await self.chatter._listen(grammar, stop=stop, max_s=6.0)
                    if cid not in house.confirmations:
                        return                        # answered on a phone meanwhile
                    if spoke or not text:
                        if attempt == 0 and not spoke:
                            continue
                        return
                    if await self._answer_question(text, {"id": cid, "options": ev.get("options") or [],
                                                          "room": (ev.get("context") or {}).get("room")}):
                        return
                    if ev.get("allow_name") and await self._new_name(cid, text, conf, stop):
                        return
                    if attempt == 0:
                        await self.reply("Non ho capito: puoi ripetere?", "Sorry, could you say that again?")
        finally:
            self._asking_stop.pop(cid, None)
            await self.ctx.actions.thinking(False)

    async def _new_name(self, cid: str, text: str, conf: float, stop: asyncio.Event) -> bool:
        """The answer to "who is it?" is a name the house does not know yet: check it, then use it."""
        candidate = name_from_speech(text)
        if conf < NAME_CONFIDENCE or len(candidate) < 2:
            return False
        await self.reply(f"Si chiama {candidate}, giusto?", f"The name is {candidate}, right?")
        verdict = None
        for attempt in range(2):
            answer, _, _, spoke = await self.chatter._listen(yes_no_grammar(self.lang), stop=stop, max_s=5.0)
            if cid not in self.ctx.house.confirmations:
                return True
            verdict = None if spoke else yes_or_no(answer, self.lang, strict=True)
            if verdict is not None or attempt:
                break
            await self.reply(f"Dimmi sì o no: si chiama {candidate}?", f"Say yes or no: is the name {candidate}?")
        if not verdict:
            return False
        if self.ctx.house.answer(cid, {"name": candidate}, by="voice"):
            await self.reply(f"Piacere, {candidate}!", f"Nice to meet you, {candidate}!")
        return True

    def _question_grammar(self) -> list[str]:
        words = []
        for o in self.question["options"]:
            label = o.get("label") or {}
            words.append(label.get(self.lang) or label.get("it") or "")
        return [w for w in words if w] + YES[self.lang] + NO[self.lang]

    async def _answer_question(self, text: str, q: dict[str, Any] | None = None) -> bool:
        q = q or self.question
        if not q:
            return False
        t = f" {normalize(text)} "
        labels = [[w for w in (o.get("label") or {}).values() if w] for o in q["options"]]
        said = [q["options"][i] for i in said_options(text, labels)]     # "non è Viola, è Rosaria": Rosaria
        if not said and any(f" {normalize(w)} " in t for words in labels for w in words):
            return False                              # only denied: "né Viola né Rosaria", "non è Viola"
        both = len(said) >= 2 and not any(f" {w} " in t for w in OR) or \
            len(q["options"]) >= 2 and any(self._said_not_denied(t, p) for p in BOTH[self.lang])
        if both:
            chosen = said if len(said) >= 2 else q["options"]
            ids = [o.get("value") for o in chosen if isinstance(o.get("value"), str)]
            if self.ctx.house.answer(q["id"], {"together": ids}, by="voice"):
                names = [self.ctx.identities.name_of(i) for i in ids]
                room = q.get("room")
                await self.reply(*V.said_each(
                    "who.together", V.TOGETHER,
                    {"names": answers.join(names, "it"), "where": answers.room(self.ctx, room, "it") if room else "lì"},
                    {"names": answers.join(names, "en"), "where": answers.room(self.ctx, room, "en") if room else "there"}))
            return True
        if said:
            if self.ctx.house.answer(q["id"], said[0].get("value"), by="voice"):
                await self.reply("Grazie!", "Thanks!")
            return True
        return False

    @staticmethod
    def _said_not_denied(t: str, phrase: str) -> bool:
        """The phrase is in the (normalized, padded) text, and not right after a denial: "non sono tutti e due"."""
        p = f" {normalize(phrase)} "
        i = t.find(p)
        while i >= 0:
            if not set(t[:i].split()[-2:]) & DENY:
                return True
            i = t.find(p, i + 1)
        return False

    # ================================================================ chatty mode
    def _on_count(self, ev) -> None:
        """A crowd in the living room or in the garden: the house offers a party or the barbecue, at most once
        in 10 minutes, and listens for the answer like after its questions."""
        if self.ctx.settings.get("voice.verbosity") != "chatty":
            return
        now = time.time()
        if now - self._last_proposal < 600:
            return
        for p in PROPOSALS:
            if ev.get("room") == p["room"] and ev.get("persons", 0) >= p["persons"] and self.chatter.can_propose(p):
                self._last_proposal = now
                self._spawn(self.chatter.propose(p))
                return

    # ================================================================ diagnostics
    async def mic_test(self) -> dict[str, Any]:
        await self._yield_mic()
        stop = asyncio.Event()
        asyncio.get_running_loop().call_later(3.0, stop.set)
        audio = await self.mic.listen(stop, max_s=3.5)
        samples = np.frombuffer(audio[: len(audio) // 2 * 2], dtype="<i2") if audio else np.zeros(1)
        level = float(np.sqrt(np.mean((samples / 32768.0) ** 2))) if samples.size else 0.0
        text, conf = await self._recognize(audio, None)
        return {"seconds": len(audio) / 2 / MIC_RATE, "level": round(level, 4),
                "peak": round(float(np.max(np.abs(samples))) / 32768.0, 3) if samples.size else 0,
                "heard": text, "confidence": round(conf, 2)}
