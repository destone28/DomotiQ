# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The conversations of the house.

- **Talk** (held down): the house listens while the button is held, then
  answers the question or runs the command.
- **Intercom**: ding-dong, "Who is it?", and a name. A known name is given
  to the next figurine that comes in through the front door; a new name
  registers a new character.
- **Questions of the house**: when the house is unsure who someone is, it
  asks aloud and on the web app; the next answer settles it.
- **Small talk** (chatter.py): the welcome of a new phone, and the questions
  of chatty mode, answered without pressing Talk.

Only one conversation at a time; pressing Talk while the house speaks
interrupts it.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

import numpy as np

from ..audio.mic import MIC_RATE, Microphone
from ..identities import NameTaken
from ..model import CATEGORY_NAMES
from ..scenes import scene_name
from . import answers, memory
from .chatter import NAME_CONFIDENCE, WELCOME, Chatter, yes_no_grammar, yes_or_no
from .narrator import Narrator
from .stories import StoryTeller
from .intents import Intent, find_name, find_room, name_from_speech, normalize, parse
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

FREQUENT = {
    "it": ["Chi è?", "Scusa, non ho capito. Chi sei?", "Vediamo...", "Non ho capito.", "Si balla!",
           "Festa finita!", "Accendo il barbecue!", "Italiano", "Come si chiama?", "In che stanza l'hai messo?"],
    "en": ["Who is it?", "Sorry, I didn't catch that. Who are you?", "Let me see...", "I didn't get that.",
           "Let's dance!", "The party is over!", "Lighting the barbecue!", "English", "What's the name?",
           "Which room did you put it in?"],
}
for _lang in ("it", "en"):
    FREQUENT[_lang].append(WELCOME[_lang])


class Voice:
    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        self.speaker = Speaker()
        self.listener = None if ctx.args.no_voice else Listener(ctx.paths.models)
        audio = ctx.audio
        device = audio.device if audio is not None and not audio.dry else None
        # the microphone is on the same USB sound card: it follows the output if that is found later
        self.mic = Microphone(device, follow=(lambda: audio.device if not audio.dry else None) if audio else None)
        self.llm = None if ctx.args.no_llm else LanguageModel()
        self.llm_ok = False
        self._jokes = random.randrange(100)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self.busy = asyncio.Lock()
        self._talk_stop: asyncio.Event | None = None
        self._talk_task: asyncio.Task | None = None
        self.expect_entrance: dict[str, Any] | None = None   # a name waiting for the front door
        self.question: dict[str, Any] | None = None           # a confirmation asked aloud
        self._asking: asyncio.Task | None = None               # asking it and listening for the answer
        self._asking_stop: dict[str, asyncio.Event] = {}       # confirmation -> stop listening (answered)
        self._last_proposal = 0.0
        self.last_chatter = float("-inf")      # monotonic: the last chatty line, comment or question
        self.in_flight = 0                     # sentences being synthesized or played now
        self.voice_end = float("-inf")         # monotonic: when the last one ended
        self._tasks: set[asyncio.Task] = set()
        bus = ctx.bus
        bus.subscribe("confirm", self._on_confirm)
        bus.subscribe("confirm_closed", self._on_confirm_closed)
        bus.subscribe("room_enter", self._on_room_enter)
        bus.subscribe("track_appear", self._on_track_appear)
        bus.subscribe("registered", self._on_registered)
        bus.subscribe("count_changed", self._on_count)
        self.chatter = Chatter(self)
        self.narrator = Narrator(self)
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
        warmed = False
        while True:
            if self.llm is not None:
                loop = asyncio.get_running_loop()
                self.llm_ok = await loop.run_in_executor(None, self.llm.health)
                if self.llm_ok and not warmed:
                    warmed = True
                    await loop.run_in_executor(None, self.llm.warm)
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
        if self.ctx.audio is not None and not (self.ctx.sim.enabled and self.ctx.sim.mute):
            await self.ctx.audio.play_voice(samples)
        else:
            await asyncio.sleep(len(samples) / 22050)

    async def say(self, text: str, level: str = "normal") -> None:
        await self.ctx.actions.say(text, level=level)

    async def reply(self, text_it: str, text_en: str | None = None) -> None:
        await self.ctx.actions.say({"it": text_it, "en": text_en or text_it})

    async def _beep(self, name: str) -> None:
        if self.ctx.audio is not None:
            await self.ctx.audio.effect(name)

    # ================================================================ listening
    async def _listen(self, grammar: list[str] | None, *, stop: asyncio.Event | None = None,
                      max_s: float = 5.0, auto_end: bool = True) -> tuple[str, float, bytes]:
        """Record and recognize. With `auto_end`, stop after a pause following speech."""
        if not (self.listener and self.listener.ok):
            return "", 0.0, b""
        loop = asyncio.get_running_loop()
        lang = self.lang
        session = await loop.run_in_executor(self.pool, self.listener.session, lang, grammar)
        stop = stop or asyncio.Event()
        state = {"speech": False, "quiet": 0.0}
        feeds: list[asyncio.Future] = []

        def on_chunk(chunk: bytes) -> None:
            feeds.append(loop.run_in_executor(self.pool, session.feed, chunk))
            if auto_end:
                level = self.mic.last_level
                if level > 0.02:
                    state["speech"], state["quiet"] = True, 0.0
                elif state["speech"]:
                    state["quiet"] += 0.1
                    if state["quiet"] >= 0.8:
                        stop.set()

        self.ctx.bus.publish("listening", on=True)
        await self.ctx.actions.update_leds(listening=True)
        try:
            audio = await self.mic.listen(stop, on_chunk, max_s=max_s)
        finally:
            self.ctx.bus.publish("listening", on=False)
            await self.ctx.actions.update_leds()
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

    # ================================================================ understanding
    async def handle(self, text: str) -> None:
        lang = self.lang
        names = self._names()
        if self.question and await self._answer_question(text):
            return
        intent = parse(text, names)
        if intent is None and self.stories.knows(text):
            intent = Intent("other", {}, 0.8, "rules")      # bills, insurance, chores...: the life of the house
        if intent is None and self.llm is not None:
            filler = asyncio.create_task(self.say("Vediamo..." if lang == "it" else "Let me see..."))
            intent = await self.llm.understand(text, names)
            await filler
            # the small model may misunderstand: questions are answered at once (at worst the right
            # answer to another question), actions are asked first unless it was quite sure
            if intent is not None and intent.name in ACTIONS and intent.confidence < SURE:
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
        await self.execute(intent)

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
            await act.light(room, a.get("color", "warm"))
            await self.reply("Fatto.", "Done.")
        elif name == "lights_off":
            await act.lights_off(a.get("room", "all"))
            await self.reply("Spento.", "Off.")
        elif name == "scene":
            greeting = a.get("greeting")
            await act.scene(a.get("scene", "normal"), announce=not greeting)
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
                    self.expect_entrance = {"identity": ident.id, "name": ident.name, "until": time.time() + 60}
                    await self.reply(f"Ciao {ident.name}, entra pure!", f"Hi {ident.name}, come on in!")
                else:
                    await self._register_named(name, origin="intercom")
            finally:
                await ctx.actions.update_leds()

    async def _ask_name(self, allow_new: bool) -> str | None:
        """Listen for a name; a known one through the grammar, a new one from free speech."""
        names = self._names()
        for attempt in range(2):
            text, conf, audio = await self._listen(names + YES[self.lang] if names else None, max_s=5.0)
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
        text, _, _ = await self._listen(YES[self.lang] + NO[self.lang], max_s=4.0)
        t = normalize(text)
        return any(t.startswith(normalize(y)) for y in YES[self.lang])

    async def _register_named(self, name: str, origin: str, room: str | None = None) -> None:
        ctx = self.ctx
        if ctx.identities.by_name(name):
            await self.reply(f"C'è già qualcuno che si chiama {name}: aggiungi un soprannome dalla webapp.",
                             f"Someone is already called {name}: add a nickname from the web app.")
            return
        if origin == "intercom":
            # whoever comes in through the front door in the next minute is the new one
            self.expect_entrance = {"new": name, "until": time.time() + 60}
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
        text, _, _ = await self._listen(rooms, max_s=4.0)
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
        exp = self.expect_entrance
        if not exp or time.time() > exp["until"]:
            self.expect_entrance = None
            return
        if ev.get("room") not in ("living", "driveway") or ev.get("category") not in ("person", None):
            return
        if kind == "room_enter" and ev.get("other") not in ("driveway", None):
            return
        track = self.ctx.house.tracks.get(ev.get("track"))
        if not track:
            return
        if "new" in exp:
            # a new character announced at the intercom: the first stranger through the door
            if track.identity or ev.get("room") != "living":
                return
            self.expect_entrance = None
            try:
                self.ctx.registration.start(exp["new"], origin="intercom", room="living", track=track.id, auto=True)
            except (NameTaken, ValueError):
                pass
            return
        if track.identity and track.identity != exp["identity"] and not track.uncertain:
            seen = self.ctx.identities.name_of(track.identity)
            self._spawn(self.reply(f"Mmm, a me sembri {seen}, non {exp['name']}!",
                                   f"Hmm, you look like {seen} to me, not {exp['name']}!"))
            self.expect_entrance = None
            return
        if ev.get("room") != "living":
            return            # wait until it is through the door
        if track.virtual:
            obj = self.ctx.sim.objects.get(track.id)
            if obj:
                obj.identity, obj.name = exp["identity"], exp["name"]
        else:
            self.ctx.vision.assign(track.id, exp["identity"])
        track.identity, track.uncertain = exp["identity"], False
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
                labels = [((o.get("label") or {}).get(self.lang) or "") for o in ev.get("options") or []]
                grammar = [w for w in labels if w] + yes_no_grammar(self.lang)
                for attempt in range(2):
                    text, conf, _, spoke = await self.chatter._listen(grammar, stop=stop, max_s=6.0)
                    if cid not in house.confirmations:
                        return                        # answered on a phone meanwhile
                    if spoke or not text:
                        if attempt == 0 and not spoke:
                            continue
                        return
                    if await self._answer_question(text, {"id": cid, "options": ev.get("options") or []}):
                        return
                    if ev.get("allow_name") and await self._new_name(cid, text, conf, stop):
                        return
                    if attempt == 0:
                        await self.reply("Non ho capito: puoi ripetere?", "Sorry, could you say that again?")
        finally:
            self._asking_stop.pop(cid, None)

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
        for o in q["options"]:
            label = o.get("label") or {}
            for word in label.values():
                if word and f" {normalize(word)} " in t:
                    if self.ctx.house.answer(q["id"], o.get("value"), by="voice"):
                        await self.reply("Grazie!", "Thanks!")
                    return True
        return False

    # ================================================================ chatty mode
    def _on_count(self, ev) -> None:
        if self.ctx.settings.get("voice.verbosity") != "chatty":
            return
        now = time.time()
        if now - self._last_proposal < 600:
            return
        if ev.get("room") == "living" and ev.get("persons", 0) >= 3:
            self._last_proposal = now
            self._spawn(self.ctx.actions.say({"it": "Siete in tanti in soggiorno: facciamo festa?",
                                              "en": "So many of you in the living room: shall we party?"}, level="chatty"))
        elif ev.get("room") == "garden" and ev.get("persons", 0) >= 2:
            self._last_proposal = now
            self._spawn(self.ctx.actions.say({"it": "Che bella giornata in giardino: accendo il barbecue?",
                                              "en": "Lovely day in the garden: shall I light the barbecue?"}, level="chatty"))

    # ================================================================ diagnostics
    async def mic_test(self) -> dict[str, Any]:
        stop = asyncio.Event()
        asyncio.get_running_loop().call_later(3.0, stop.set)
        audio = await self.mic.listen(stop, max_s=3.5)
        samples = np.frombuffer(audio[: len(audio) // 2 * 2], dtype="<i2") if audio else np.zeros(1)
        level = float(np.sqrt(np.mean((samples / 32768.0) ** 2))) if samples.size else 0.0
        text, conf = await self._recognize(audio, None)
        return {"seconds": len(audio) / 2 / MIC_RATE, "level": round(level, 4),
                "peak": round(float(np.max(np.abs(samples))) / 32768.0, 3) if samples.size else 0,
                "heard": text, "confidence": round(conf, 2)}
