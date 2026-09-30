# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Stories and free answers made up by a language model, with characters that stay themselves.

A second llama-server (domotiq-story, port 8082) runs a model that writes
Italian and English better than the one that understands the commands, with
its own cache and its own two cores.

- **Personalities.** The first time a character is needed, the model gives it
  a job, a character, a passion and a quirk, keeping what the staff told the
  house about it (the facts of the character, from the web app or "ricorda
  che..."). They stay the same until the house restarts; new facts make the
  personality again.
- **Always a new story.** A different idea each time, and the beginnings of
  the stories already told, to avoid.
- **The life of the house.** What the house makes up when asked ("the car
  insurance expires in March") is kept and given back to the model, so that
  the next answers agree with it.
- **Speed.** On the UNO Q the model reads about 8 words a second and writes
  about 5, so a story made on request would start after half a minute. The
  storyteller therefore writes ahead, while nobody asks anything: a story for
  each character in the house, one about anybody, and the lines of chatty
  mode (anecdotes, memories, questions with the answer to a yes and to a no).
  A request from a visitor stops the writing ahead at once. Free questions
  cannot be written ahead: for them the memory of the house (personalities
  and made-up facts) stays read in a slot of the model of its own, so only
  the question has to be read.
- **Spoken while it is written.** A story made on request is spoken sentence
  by sentence while the model writes it, and the next sentence is
  synthesized while one plays. Every sentence is read by the voice of the
  language it is written in, and the room it talks about lights up.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import TYPE_CHECKING, Any, Callable, Iterator

from ..model import CATEGORY_NAMES
from .intents import find_room, normalize

if TYPE_CHECKING:
    from .manager import Voice

log = logging.getLogger(__name__)

URL = os.environ.get("DOMOTIQ_STORY_URL", "http://127.0.0.1:8082")
LIVE_SLOT, AHEAD_SLOT = 0, 1  # llama-server runs with two slots: requests, and writing ahead
STORY_TOKENS = 220            # about five sentences
ANSWER_TOKENS = 80            # one or two sentences
PERSONA_TOKENS = 40
AHEAD_EVERY_S = 4.0
LIVE_MIN_RATE = 3.5           # tokens a second needed to speak a story while it is written
MAX_PENDING = 2               # stories or answers promised "in a moment" at the same time
DELIVER_WAIT_S = 300.0
MAX_AHEAD_CAST = 4            # stories written ahead for at most this many characters in the house

SYSTEM = {
    "it": ("Sei la voce di una piccola casa intelligente, un plastico esposto in una fiera. In casa vivono dei "
           "personaggi: statuine che i visitatori spostano tra le stanze (cucina, soggiorno, camera da letto, bagno, "
           "locale tecnico, garage, giardino). Parli in italiano semplice e corretto, con frasi brevi, in modo "
           "allegro e adatto ai bambini. Niente titoli, elenchi, emoji o parole straniere. Non contraddire mai quello "
           "che si sa già dei personaggi e della casa."),
    "en": ("You are the voice of a small smart house, a model shown at a fair. Characters live in the house: "
           "figurines that visitors move between the rooms (kitchen, living room, bedroom, bathroom, utility room, "
           "garage, garden). You speak simple, correct English, in short sentences, cheerful and suitable for "
           "children. No titles, lists, emoji or foreign words. Never contradict what is already known about the "
           "characters and the house."),
}
# the seeds only steer the model towards different stories; the story itself is all written by it
SEEDS = {
    "it": ["un mistero da risolvere", "un regalo inaspettato", "un piccolo disastro in cucina", "una gara buffa",
           "un animale che non doveva esserci", "un blackout", "una sorpresa per qualcuno", "un oggetto perduto",
           "un temporale", "una scommessa", "un invito a cena", "un'invenzione strana", "una notte senza sonno",
           "un malinteso", "una lettera misteriosa", "una festa organizzata in segreto"],
    "en": ["a mystery to solve", "an unexpected present", "a small disaster in the kitchen", "a funny contest",
           "an animal that should not be there", "a power cut", "a surprise for someone", "a lost object",
           "a thunderstorm", "a bet", "a dinner invitation", "a strange invention", "a sleepless night",
           "a misunderstanding", "a mysterious letter", "a party organised in secret"],
}
# a story must never say these aloud, whatever the model writes
BLOCKED = re.compile(r"\b(cazz|merd|stronz|puttan|vaffancul|coglion|fuck|shit|bitch|bastard|asshole|kill|uccid|"
                     r"sangue|blood|morto|morti|dead|pistol|gun|droga|drug)\w*", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”»]?\s+")
ABBREVIATIONS = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|St|Prof|Sig|Sigg|Dott|Ing|Avv)|\b[A-Z])\.$")
# every sentence is read by the voice of its own language, also when the model slips into the other one
LANG_WORDS = {
    "it": {"il", "lo", "la", "gli", "le", "un", "una", "che", "di", "del", "della", "e", "è", "non", "per", "con",
           "sono", "era", "erano", "mentre", "poi", "anche", "nella", "nel", "alla", "al", "quando", "perché",
           "tutti", "suo", "sua", "loro", "ma", "si", "da", "ha", "aveva", "casa"},
    "en": {"the", "a", "an", "and", "is", "was", "were", "of", "to", "in", "on", "with", "he", "she", "they",
           "it", "his", "her", "their", "but", "when", "then", "there", "that", "this", "had", "has", "house"},
}
# a personality: labelled fields (a small model fills a labelled form much better than a bare list)
LABELS = {"it": ("lavoro", "carattere", "passione", "mania"), "en": ("job", "character", "passion", "quirk")}


def persona_grammar(lang: str, pet: bool) -> str:
    labels = LABELS[lang][1:] if pet else LABELS[lang]
    body = ' "; " '.join(f'"{label}: " field' for label in labels)
    return f"root ::= {body}\nfield ::= [^;\\n]{{3,40}}\n"
# a question of chatty mode, with what the house says after a yes and after a no
QUESTION_GRAMMAR = r'''root ::= "D: " line "\nSI: " line "\nNO: " line
line ::= [^\n]{8,140}
'''


def sentence_lang(sentence: str, default: str) -> str:
    words = re.findall(r"[a-zàèéìòù']+", sentence.lower())
    score = {lang: sum(1 for w in words if w in vocab) for lang, vocab in LANG_WORDS.items()}
    other = "en" if default == "it" else "it"
    return other if score[other] >= score[default] + 2 else default


def split_sentences(text: str) -> tuple[list[str], str]:
    """Complete sentences and the rest; "Mr." or "Dott." do not end a sentence."""
    parts = SENTENCE_END.split(text)
    done: list[str] = []
    carry = ""
    for part in parts[:-1]:
        carry = f"{carry} {part}".strip() if carry else part
        if ABBREVIATIONS.search(carry):
            continue
        done.append(carry)
        carry = ""
    rest = f"{carry} {parts[-1]}".strip() if carry else parts[-1]
    return done, rest


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S)
    text = re.sub(r"[*_#`~>|\[\]{}]", " ", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str, limit: int) -> list[str]:
    done, rest = split_sentences(_clean(text) + " ")
    out = [s for s in (_clean(x) for x in done + ([rest] if rest.strip() else []))
           if len(s.split()) >= 2 and not BLOCKED.search(s)]
    return out[:limit]


class StoryModel:
    """The HTTP side of the second llama-server: streamed chat completions on a given slot."""

    def __init__(self, url: str = URL, timeout: float = 600.0) -> None:
        self.url = url
        self.timeout = timeout
        self.rate = 0.0                     # tokens a second of the last text written (0: not measured yet)

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=2) as r:
                return r.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def stream(self, messages: list[dict[str, str]], tokens: int, temperature: float = 0.8,
               grammar: str | None = None, stop: threading.Event | None = None,
               slot: int = LIVE_SLOT) -> Iterator[str]:
        body: dict[str, Any] = {
            "messages": messages, "stream": True, "n_predict": tokens, "max_tokens": tokens,
            "temperature": temperature, "top_p": 0.9, "repeat_penalty": 1.12, "cache_prompt": True,
            "seed": random.randrange(1 << 30), "id_slot": slot,
            "chat_template_kwargs": {"enable_thinking": False},      # the models that "think" first must not
        }
        if grammar:
            body["grammar"] = grammar
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        first, count = 0.0, 0
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            for raw in r:
                if stop is not None and stop.is_set():
                    return                      # closing the connection stops the model too
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    piece = json.loads(line[6:])["choices"][0]["delta"].get("content") or ""
                except (ValueError, KeyError, IndexError):
                    continue
                if piece:
                    count += 1
                    if count == 1:
                        first = time.monotonic()
                    elif count >= 12:
                        self.rate = (count - 1) / max(0.001, time.monotonic() - first)
                    yield piece

    def complete(self, messages: list[dict[str, str]], tokens: int, temperature: float = 0.7,
                 grammar: str | None = None, stop: threading.Event | None = None, slot: int = LIVE_SLOT) -> str:
        return "".join(self.stream(messages, tokens, temperature, grammar, stop, slot))


class StoryTeller:
    def __init__(self, voice: "Voice", model: StoryModel | None = None) -> None:
        self.voice = voice
        self.ctx = voice.ctx
        self.model = model or StoryModel()
        self.ok = False
        self.task: asyncio.Task | None = None       # a story or an answer being spoken (Talk stops it)
        self.rng = random.Random()
        # what the house has made up since it started: forgotten at the next restart
        self.personas: dict[str, dict[str, str]] = {}          # identity -> {lang: "medico; distratto; ..."}
        self._facts_seen: dict[str, tuple[str, ...]] = {}      # the facts each personality was made with
        self.told: dict[str, deque[str]] = {}                   # identity, pair or room -> beginnings already told
        self.lore: deque[str] = deque(maxlen=10)                # things made up about the life of the house
        # written ahead: key -> {"lang", "sentences", "cast", "facts", ...}
        self.ahead: dict[str, dict[str, Any]] = {}
        self._pending_reply: dict[str, dict[str, str]] = {}     # identity -> {"yes", "no"} of the last question
        self._ahead_stop = threading.Event()
        self._ahead_busy = False
        self._live = 0                                          # requests of visitors being served
        self._warm_key = ""                                     # the memory already read in the live slot
        self._pending = 0                                       # stories and answers promised for later

    @property
    def lang(self) -> str:
        return self.voice.lang

    @property
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    async def check(self) -> bool:
        loop = asyncio.get_running_loop()
        self.ok = await loop.run_in_executor(None, self.model.health)
        return self.ok

    def reset(self) -> None:
        """Back to the personalities the staff gave (what a restart does)."""
        self.personas.clear()
        self._facts_seen.clear()
        self.told.clear()
        self.lore.clear()
        self.ahead.clear()
        self._pending_reply.clear()
        self._warm_key = ""

    async def preempt(self) -> None:
        """Talk wants the house: the story stops."""
        task = self.task
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        await asyncio.wait({task}, timeout=2.0)

    # ================================================================ model calls
    async def _call(self, messages: list[dict[str, str]], tokens: int, temperature: float = 0.8,
                    grammar: str | None = None, ahead: bool = False) -> str:
        loop = asyncio.get_running_loop()
        stop = self._ahead_stop if ahead else None
        slot = AHEAD_SLOT if ahead else LIVE_SLOT
        try:
            return await loop.run_in_executor(None, lambda: self.model.complete(
                messages, tokens, temperature, grammar, stop, slot))
        except (OSError, urllib.error.URLError) as e:
            log.warning("story model: %s", e)
            return ""

    class _Live:
        """A visitor asks: the writing ahead stops at once, and waits until the request is served."""

        def __init__(self, teller: "StoryTeller") -> None:
            self.teller = teller

        async def __aenter__(self) -> None:
            t = self.teller
            t._live += 1
            t._ahead_stop.set()
            for _ in range(40):                     # the model stops within a token or two
                if not t._ahead_busy:
                    break
                await asyncio.sleep(0.05)

        async def __aexit__(self, *exc: Any) -> None:
            t = self.teller
            t._live -= 1
            if t._live == 0:
                t._ahead_stop.clear()

    # ================================================================ characters
    def _kind(self, ident, lang: str) -> str:
        if ident.category == "person":
            return "persona" if lang == "it" else "person"
        return CATEGORY_NAMES.get(ident.category, {}).get(lang, ident.category)

    def _facts_changed(self, ident) -> None:
        now = tuple(ident.facts)
        if self._facts_seen.get(ident.id, now) != now:
            self.personas.pop(ident.id, None)       # the staff told something new: the personality follows it
            for key in [k for k, v in self.ahead.items() if ident.id in v.get("cast", ())]:
                self.ahead.pop(key, None)
            self._warm_key = ""
        self._facts_seen[ident.id] = now

    async def persona(self, ident, ahead: bool = False) -> str:
        """The personality of a character in the current language, made up once and then kept."""
        lang = self.lang
        self._facts_changed(ident)
        cards = self.personas.setdefault(ident.id, {})
        if lang in cards:
            return cards[lang]
        facts = "; ".join(ident.facts)
        pet = ident.category != "person"
        if cards:
            other = next(iter(cards.values()))      # made up in the other language: the same, translated
            ask = (f"Traduci in italiano, voce per voce: {other}" if lang == "it"
                   else f"Translate into English, item by item: {other}")
        elif lang == "it":
            ask = (f"Inventa la personalità di {ident.name} ({self._kind(ident, lang)}), in poche parole per voce. "
                   + (f"Deve rispettare: {facts}. " if facts else "")
                   + ("Esempio: carattere: allegro; passione: le palline; mania: abbaia ai piccioni" if pet else
                      "Esempio: lavoro: fornaio; carattere: allegro; passione: il calcio; mania: canta sotto la doccia"))
        else:
            ask = (f"Make up the personality of {ident.name} ({self._kind(ident, lang)}), a few words each. "
                   + (f"It must agree with: {facts}. " if facts else "")
                   + ("Example: character: cheerful; passion: balls; quirk: barks at pigeons" if pet else
                      "Example: job: baker; character: cheerful; passion: football; quirk: sings in the shower"))
        messages = [{"role": "system", "content": SYSTEM[lang]}, {"role": "user", "content": ask}]
        # the labels of this language also when translating: a bare "translate" kept the English ones
        card = _clean(await self._call(messages, PERSONA_TOKENS, 0.9, persona_grammar(lang, pet), ahead)).strip(" .;")
        if card and lang == self.lang:
            cards[lang] = card
            self._warm_key = ""
            log.info("personality of %s (%s): %s", ident.name, lang, card)
        return card

    def _line(self, ident) -> str:
        """What the model is told about a character: its facts first, then its personality."""
        lang = self.lang
        card = self.personas.get(ident.id, {}).get(lang, "")
        line = f"- {ident.name} ({self._kind(ident, lang)})"
        if ident.facts:
            line += (": fatti certi " if lang == "it" else ": known facts ") + "; ".join(ident.facts)
        if card:
            line += (". Personalità: " if lang == "it" else ". Personality: ") + card
        return line

    async def _lines(self, cast: list[Any], ahead: bool = False) -> list[str]:
        for ident in cast:
            await self.persona(ident, ahead)
        return [self._line(i) for i in cast]

    def _present(self) -> list[Any]:
        ids = self.ctx.identities
        out = []
        for t in self.ctx.house.tracks.values():
            ident = ids.get(t.identity) if t.identity else None
            if ident and ident not in out and t.room not in ("outside", None) and not t.carried:
                out.append(ident)
        return out

    # ================================================================ prompts
    def _story_prompt(self, lines: list[str], told: deque[str], room: str | None, party: bool) -> list[dict[str, str]]:
        lang = self.lang
        seed = self.rng.choice(SEEDS[lang])
        lore = list(self.lore)[-3:]
        if lang == "it":
            ask = ("Storia nuova, al massimo cinque frasi, al passato, con un finale allegro.\n"
                   + ("Personaggi:\n" + "\n".join(lines) + "\n" if lines else "Protagonista: la casa.\n")
                   + (f"Si svolge soprattutto in {self.ctx.layout.room_label(room, lang).lower()}.\n" if room else "")
                   + ("È la storia di una festa.\n" if party else "") + f"Spunto: {seed}.\n"
                   + ("Fatti della casa: " + " ".join(lore) + "\n" if lore else "")
                   + ("Già raccontate, non ripeterle: " + " / ".join(told) + "\n" if told else "")
                   + "Rispetta la personalità di ognuno.")
        else:
            ask = ("A new story, at most five sentences, in the past tense, with a happy ending.\n"
                   + ("Characters:\n" + "\n".join(lines) + "\n" if lines else "Main character: the house.\n")
                   + (f"It takes place mostly in the {self.ctx.layout.room_label(room, lang).lower()}.\n" if room else "")
                   + ("It is the story of a party.\n" if party else "") + f"Idea: {seed}.\n"
                   + ("Facts of the house: " + " ".join(lore) + "\n" if lore else "")
                   + ("Already told, do not repeat: " + " / ".join(told) + "\n" if told else "")
                   + "Keep everyone's personality.")
        return [{"role": "system", "content": SYSTEM[lang]}, {"role": "user", "content": ask}]

    def _memory(self) -> tuple[list[dict[str, str]], str]:
        """The memory of the house as the first turns of the conversation: kept read in the live slot."""
        lang = self.lang
        people = [self._line(i) for i in self.ctx.identities.all()
                  if i.category in ("person", "dog", "cat", "animal") and (i.facts or self.personas.get(i.id, {}).get(lang))]
        lore = list(self.lore)
        if lang == "it":
            text = ("Memoria della casa, da non contraddire.\n" + ("Personaggi:\n" + "\n".join(people) + "\n" if people else "")
                    + ("Cose già dette sulla casa:\n" + "\n".join(lore) if lore else "Ancora niente sulla vita della casa."))
            ack = "D'accordo, me lo ricordo."
        else:
            text = ("Memory of the house, not to be contradicted.\n" + ("Characters:\n" + "\n".join(people) + "\n" if people else "")
                    + ("Things already said about the house:\n" + "\n".join(lore) if lore else "Nothing yet about life in the house."))
            ack = "All right, I remember."
        turns = [{"role": "system", "content": SYSTEM[lang]}, {"role": "user", "content": text},
                 {"role": "assistant", "content": ack}]
        return turns, f"{lang}|{text}"

    # ================================================================ speaking
    async def _speak(self, sentences_or_stream, on_sentence: Callable[[str], None] | None = None) -> list[str]:
        """Speak sentences (a list, or a queue fed by the model) in order, synthesizing the next one
        while the previous one plays; every sentence with the voice of its own language."""
        lang = self.lang
        spoken = self.ctx.actions.speaks("normal")
        voice = self.voice
        # one sentence synthesized ahead of the one playing: all at once, they shared the same two cores
        ready: asyncio.Queue[tuple[str, str, Any] | None] = asyncio.Queue(maxsize=1)

        async def prepare() -> None:
            if isinstance(sentences_or_stream, list):
                for sentence in sentences_or_stream:
                    await self._queue_sentence(ready, sentence, lang, spoken)
            else:
                while True:
                    sentence = await sentences_or_stream.get()
                    if sentence is None:
                        break
                    await self._queue_sentence(ready, sentence, lang, spoken)
            await ready.put(None)

        preparer = asyncio.ensure_future(prepare())
        said: list[str] = []
        try:
            while True:
                item = await ready.get()
                if item is None:
                    break
                sentence, said_lang, samples = item
                if on_sentence:
                    on_sentence(sentence)
                said.append(sentence)
                self.ctx.bus.publish("say", text=sentence, lang=said_lang, spoken=spoken)
                if samples is not None:
                    await voice.play(samples)
        finally:
            preparer.cancel()
        return said

    async def _queue_sentence(self, ready: asyncio.Queue, sentence: str, lang: str, spoken: bool) -> None:
        sentence = _clean(sentence)
        if len(sentence.split()) < 2 or BLOCKED.search(sentence):
            return
        said_lang = sentence_lang(sentence, lang)
        samples = await self.voice.speaker.synth(sentence, said_lang) if spoken else None
        await ready.put((sentence, said_lang, samples))

    async def _speak_live(self, messages: list[dict[str, str]], tokens: int, max_sentences: int,
                          on_sentence: Callable[[str], None] | None = None) -> list[str]:
        """Speak the sentences one by one while the model writes them (live slot)."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        stop = threading.Event()

        def produce() -> None:
            buf = ""
            count = 0
            try:
                for piece in self.model.stream(messages, tokens, 0.85, stop=stop, slot=LIVE_SLOT):
                    buf += piece
                    done, buf = split_sentences(buf)
                    for sentence in done:
                        loop.call_soon_threadsafe(queue.put_nowait, sentence)
                        count += 1
                        if count >= max_sentences:
                            stop.set()
                            return
                if buf.strip() and count < max_sentences:
                    loop.call_soon_threadsafe(queue.put_nowait, buf)
            except (OSError, urllib.error.URLError) as e:
                log.warning("story model: %s", e)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = loop.run_in_executor(None, produce)
        try:
            return await self._speak(queue, on_sentence)
        finally:
            stop.set()
            await asyncio.wait({worker}, timeout=5)

    def _light_rooms(self, sentence: str) -> None:
        room = find_room(normalize(sentence))
        if room and self.ctx.layout.light_of_room(room) is not None:
            asyncio.ensure_future(self.ctx.actions.light(room, "warm", "breathe", 70, 12))

    # ================================================================ stories
    def _cast(self, names: list[str] | None) -> list[Any]:
        ids = self.ctx.identities
        cast = [i for i in (ids.by_name(n) for n in (names or [])) if i]
        if cast:
            return cast[:3]
        pool = self._present() or [i for i in ids.all() if i.category in ("person", "dog", "cat", "animal")]
        self.rng.shuffle(pool)
        return pool[: self.rng.choice((1, 2))] if pool else []

    def _fresh(self, entry: dict[str, Any] | None) -> bool:
        if not entry or entry.get("lang") != self.lang:
            return False
        for ident_id, facts in entry.get("facts", {}).items():
            ident = self.ctx.identities.get(ident_id)
            if ident is None or tuple(ident.facts) != facts:
                return False
        return True

    async def tell(self, names: list[str] | None = None, room: str | None = None, party: bool = False) -> bool:
        """A new story; False if the story model is not there."""
        if not self.ok and not await self.check():
            return False
        self.task = asyncio.current_task()
        # a story written ahead, if there is one for this request
        key = None
        if not room and not party:
            one = self.ctx.identities.by_name(names[0]) if names and len(names) == 1 else None
            key = "story:*" if not names else (f"story:{one.id}" if one else None)
        entry = self.ahead.pop(key, None) if key else None
        if self._fresh(entry):
            said = await self._speak(list(entry["sentences"]), self._light_rooms)
            cast_ids = list(entry["cast"])
        elif self.slow:
            return await self._promise("story", lambda: self._deliver_story(names, room, party))
        else:
            async with self._Live(self):
                await self.ctx.actions.say({"it": "Fammi pensare...", "en": "Let me think..."})
                cast = self._cast(names)
                cast_ids = [i.id for i in cast]
                lines = await self._lines(cast)
                told = self.told.setdefault("+".join(sorted(cast_ids)) or (room or "house"), deque(maxlen=3))
                said = await self._speak_live(self._story_prompt(lines, told, room, party), STORY_TOKENS, 6,
                                              self._light_rooms)
        return await self._after_story(said, cast_ids, room)

    async def _after_story(self, said: list[str], cast_ids: list[str], room: str | None) -> bool:
        if said:
            cast_key = "+".join(sorted(cast_ids)) or (room or "house")
            self.told.setdefault(cast_key, deque(maxlen=3)).append(" ".join(said[0].split()[:12]))
            names_told = [self.ctx.identities.name_of(i) for i in cast_ids if self.ctx.identities.get(i)]
            self.ctx.store.add_event("story", {"cast": names_told, "room": room, "sentences": len(said)})
        else:
            await self.ctx.actions.say({"it": "Oggi non mi viene in mente niente, riprova tra poco.",
                                        "en": "Nothing comes to mind today, try again in a moment."})
        await self.ctx.actions.lights_auto("all")
        return bool(said)

    # ================================================================ later
    @property
    def slow(self) -> bool:
        """The model writes slower than the house speaks (measured): stories and answers come later."""
        return self.model.rate < LIVE_MIN_RATE

    async def _promise(self, kind: str, make: Callable[[], Any]) -> bool:
        """Promise a story or an answer "in a moment", write it in the background, say it when the house is free."""
        if self._pending >= MAX_PENDING:
            await self.ctx.actions.say({"it": "Ho già delle storie da finire: chiedimelo di nuovo tra un po'!",
                                        "en": "I already have stories to finish: ask me again in a while!"})
            return True
        self._pending += 1
        text = ({"it": "La sto ancora scrivendo: te la racconto tra un paio di minuti!",
                 "en": "I'm still writing it: I'll tell you in a couple of minutes!"} if kind == "story" else
                {"it": "Bella domanda! Ci penso e te lo dico tra poco.",
                 "en": "Good question! Let me think about it, I'll tell you in a moment."})
        await self.ctx.actions.say(text)

        async def run() -> None:
            try:
                await make()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a promise that fails is simply not kept
                log.exception("story or answer for later failed")
            finally:
                self._pending -= 1
        self.voice._spawn(run())
        return True

    async def _when_free(self) -> bool:
        end = time.monotonic() + DELIVER_WAIT_S
        v = self.voice
        while time.monotonic() < end:
            speaking = self.ctx.audio is not None and self.ctx.audio.speaking
            if not v.busy.locked() and not speaking and not v.in_flight:
                return True
            await asyncio.sleep(1.0)
        return False

    async def _deliver_story(self, names: list[str] | None, room: str | None, party: bool) -> None:
        async with self._Live(self):
            cast = self._cast(names)
            cast_ids = [i.id for i in cast]
            lines = await self._lines(cast)
            told = self.told.setdefault("+".join(sorted(cast_ids)) or (room or "house"), deque(maxlen=3))
            text = await self._call(self._story_prompt(lines, told, room, party), STORY_TOKENS, 0.85)
        sentences = _sentences(text, 6)
        if not sentences or not await self._when_free():
            return
        async with self.voice.busy:
            self.task = asyncio.current_task()
            await self.ctx.actions.say({"it": "Ecco la storia che mi avevi chiesto!", "en": "Here is the story you asked me for!"})
            said = await self._speak(sentences, self._light_rooms)
            await self._after_story(said, cast_ids, room)

    async def _deliver_answer(self, question: str, names: list[str] | None, memory: bool) -> None:
        async with self._Live(self):
            messages = await self._answer_prompt(question, names, memory)
            text = await self._call(messages, ANSWER_TOKENS, 0.85)
        sentences = _sentences(text, 3)
        if not sentences or not await self._when_free():
            return
        async with self.voice.busy:
            self.task = asyncio.current_task()
            await self.ctx.actions.say({"it": "Ecco la risposta alla domanda di prima.", "en": "Here is the answer to the question you asked."})
            said = await self._speak(sentences)
        if said:
            self.lore.append(f"({question.strip()[:70]}) {' '.join(said)[:160]}")
            self._warm_key = ""

    # ================================================================ free answers
    async def answer(self, question: str, names: list[str] | None = None, memory: bool = False) -> bool:
        """A free answer about the life of the house, kept so that the next ones agree with it."""
        if not self.ok and not await self.check():
            return False
        self.task = asyncio.current_task()
        if self.slow:
            return await self._promise("answer", lambda: self._deliver_answer(question, names, memory))
        async with self._Live(self):
            said = await self._speak_live(await self._answer_prompt(question, names, memory), ANSWER_TOKENS, 3)
        if said:
            self.lore.append(f"({question.strip()[:70]}) {' '.join(said)[:160]}")
            self._warm_key = ""
        return bool(said)

    async def _answer_prompt(self, question: str, names: list[str] | None, memory: bool) -> list[dict[str, str]]:
        lang = self.lang
        ids = self.ctx.identities
        for ident in [i for i in (ids.by_name(n) for n in (names or [])) if i]:
            await self.persona(ident)
        turns, _ = self._memory()
        if lang == "it":
            ask = (f"Un visitatore chiede: \"{question}\"\n"
                   + ("È un ricordo: raccontalo con qualche dettaglio, come se fosse successo davvero. " if memory else "")
                   + "Rispondi come la casa, in una o due frasi brevi. Sulla casa e sui personaggi inventa pure, "
                     "restando coerente con la memoria. Sul mondo fuori dalla casa di' che sei una casa e non lo sai.")
        else:
            ask = (f"A visitor asks: \"{question}\"\n"
                   + ("It is a memory: tell it with some details, as if it really happened. " if memory else "")
                   + "Answer as the house, in one or two short sentences. About the house and the characters, make "
                     "things up freely but agree with the memory. About the world outside, say you are a house and don't know.")
        return turns + [{"role": "user", "content": ask}]

    async def about(self, name: str) -> str:
        """What the house knows (and has made up) about a character."""
        lang = self.lang
        ident = self.ctx.identities.by_name(name)
        if not ident:
            return (f"Non conosco nessuno che si chiama {name}." if lang == "it" else f"I don't know anyone called {name}.")
        parts = []
        if ident.facts:
            parts.append("; ".join(ident.facts))
        card = ""
        if self.ok or await self.check():
            async with self._Live(self):
                card = await self.persona(ident)
        if card:
            parts.append(". ".join(p.strip()[:1].upper() + p.strip()[1:] for p in card.split(";") if p.strip()))
        if not parts:
            kind = ("una persona" if ident.category == "person" else "un " + self._kind(ident, lang)) if lang == "it" \
                else f"a {self._kind(ident, lang)}"
            return (f"Di {ident.name} so solo che è {kind}. Dimmi qualcosa: ricorda che {ident.name}..." if lang == "it"
                    else f"All I know about {ident.name} is that it's {kind}. Tell me more: remember that {ident.name}...")
        return (f"Di {ident.name} so questo: {'. '.join(parts)}." if lang == "it"
                else f"Here is what I know about {ident.name}: {'. '.join(parts)}.")

    # ================================================================ chatty mode
    CHAT = {
        "anecdote": {
            "it": "Racconta in due frasi brevi un piccolo aneddoto divertente su {name}.",
            "en": "Tell in two short sentences a small funny anecdote about {name}.",
        },
        "memory": {
            "it": ("Ricorda ad alta voce, in due frasi brevi, un episodio del passato della casa con {name}: una festa, "
                   "un compleanno o una vacanza, con una data precisa. Comincia con \"Vi ricordate\"."),
            "en": ("Recall aloud, in two short sentences, an episode from the past of the house with {name}: a party, "
                   "a birthday or a holiday, with a precise date. Start with \"Do you remember\"."),
        },
        "question": {
            "it": ("Scrivi una domanda breve a {name} sulla vita di casa (bollette, spesa, scadenze, faccende, compleanni, "
                   "animali), chiamandolo per nome; poi cosa risponde la casa se dice sì, e se dice no. Formato:\n"
                   "D: la domanda\nSI: la risposta a un sì\nNO: la risposta a un no"),
            "en": ("Write a short question to {name} about life in the house (bills, shopping, deadlines, chores, "
                   "birthdays, pets), calling them by name; then what the house says after a yes, and after a no. Format:\n"
                   "D: the question\nSI: the reply to a yes\nNO: the reply to a no"),
        },
    }

    async def _write_chat(self, ident, kind: str, ahead: bool) -> dict[str, Any] | None:
        lang = self.lang
        lines = await self._lines([ident], ahead)
        lore = list(self.lore)[-3:]
        ask = (self.CHAT[kind][lang].format(name=ident.name) + "\n" + ("Personaggio:\n" if lang == "it" else "Character:\n")
               + "\n".join(lines)
               + (("\nFatti della casa: " if lang == "it" else "\nFacts of the house: ") + " ".join(lore) if lore else ""))
        messages = [{"role": "system", "content": SYSTEM[lang]}, {"role": "user", "content": ask}]
        if kind == "question":
            text = await self._call(messages, 110, 0.9, QUESTION_GRAMMAR, ahead)
            m = re.match(r"D: (.+)\nSI: (.+)\nNO: (.+)", text.strip())
            if not m or BLOCKED.search(text):
                return None
            q, yes, no = (_clean(x) for x in m.groups())
            return {"lang": lang, "sentences": [q], "yes": yes, "no": no, "cast": [ident.id],
                    "facts": {ident.id: tuple(ident.facts)}}
        text = await self._call(messages, ANSWER_TOKENS, 0.9, None, ahead)
        sentences = _sentences(text, 3)
        if not sentences:
            return None
        return {"lang": lang, "sentences": sentences, "cast": [ident.id], "facts": {ident.id: tuple(ident.facts)}}

    def chat_ready(self, identity: str) -> list[str]:
        """The kinds of chatty line already written for a character (with a slow model, only those are used)."""
        return [k for k in ("anecdote", "memory", "question")
                if self._fresh(self.ahead.get(f"chat:{k}:{identity}"))]

    async def chat(self, ident, room: str | None, kind: str) -> list[str]:
        """A line of small talk about a character in the house (chatty mode); returns what was said."""
        if not self.ok and not await self.check():
            return []
        self.task = asyncio.current_task()
        entry = self.ahead.pop(f"chat:{kind}:{ident.id}", None)
        if not self._fresh(entry):
            async with self._Live(self):
                entry = await self._write_chat(ident, kind, ahead=False)
        if not entry:
            return []
        if kind == "question":
            self._pending_reply[ident.id] = {"yes": entry["yes"], "no": entry["no"]}
        said = await self._speak(list(entry["sentences"]))
        if said and kind == "memory":
            self.lore.append(" ".join(said)[:160])
            self._warm_key = ""
        return said

    async def chat_reply(self, ident, question: str, answer: str) -> list[str]:
        """After a visitor answered for a character: the reply written with the question, for a yes or a no."""
        from .chatter import yes_or_no            # here: chatter imports this module
        replies = self._pending_reply.pop(ident.id, None) or {}
        verdict = yes_or_no(answer, self.lang, strict=True) if answer else None
        if verdict is None:
            text = ({"it": "Ah, interessante!", "en": "Oh, interesting!"} if answer
                    else {"it": f"Va bene {ident.name}, me lo dirai un'altra volta.",
                          "en": f"All right {ident.name}, you can tell me another time."})[self.lang]
        else:
            text = replies.get("yes" if verdict else "no") or ({"it": "D'accordo!", "en": "All right!"}[self.lang])
        said = await self._speak([text])
        if answer:
            what = ("sì" if self.lang == "it" else "yes") if verdict else ("no" if verdict is False else answer[:60])
            self.lore.append(f"({question[:70]}) {ident.name}: {what}.")
            self._warm_key = ""
        return said

    # ================================================================ writing ahead
    async def run_ahead(self) -> None:
        """Write stories and chatty lines while nobody asks anything (started with the voice)."""
        while True:
            await asyncio.sleep(AHEAD_EVERY_S)
            if not self.ok or self._live or self.voice.busy.locked():
                continue
            try:
                self._ahead_busy = True
                await self._ahead_step()
            except Exception:  # noqa: BLE001 - writing ahead must never stop
                log.exception("writing ahead failed")
            finally:
                self._ahead_busy = False

    async def _ahead_step(self) -> None:
        for key in [k for k, v in self.ahead.items() if not self._fresh(v)]:
            self.ahead.pop(key, None)
        present = self._present()[:MAX_AHEAD_CAST]
        # 1. the personalities of the characters in the house
        for ident in present:
            if self.lang not in self.personas.get(ident.id, {}) or tuple(ident.facts) != self._facts_seen.get(ident.id):
                await self.persona(ident, ahead=True)
                return
        # 2. the memory of the house read in the live slot, so that a free question starts at once
        turns, warm_key = self._memory()
        if warm_key != self._warm_key:
            await self._call(turns + [{"role": "user", "content": "OK?"}], 1, 0.0, None, ahead=False)
            if not self._ahead_stop.is_set():
                self._warm_key = warm_key
            return
        # 3. a story for each character in the house, and one about anybody
        for ident in present:
            if f"story:{ident.id}" not in self.ahead:
                await self._write_story(f"story:{ident.id}", [ident])
                return
        if "story:*" not in self.ahead and self._cast(None):
            await self._write_story("story:*", self._cast(None))
            return
        # 4. the lines of chatty mode, for the characters in the house
        if self.ctx.settings.get("voice.verbosity") == "chatty":
            for ident in present:
                for kind in ("question", "anecdote", "memory"):
                    key = f"chat:{kind}:{ident.id}"
                    if key not in self.ahead:
                        entry = await self._write_chat(ident, kind, ahead=True)
                        if entry and not self._ahead_stop.is_set() and entry["lang"] == self.lang:
                            self.ahead[key] = entry
                        return

    async def _write_story(self, key: str, cast: list[Any]) -> None:
        lines = await self._lines(cast, ahead=True)
        if self._ahead_stop.is_set():
            return
        told = self.told.setdefault("+".join(sorted(i.id for i in cast)) or "house", deque(maxlen=3))
        started = time.monotonic()
        text = await self._call(self._story_prompt(lines, told, None, False), STORY_TOKENS, 0.85, None, ahead=True)
        if self._ahead_stop.is_set():
            return                                  # interrupted: a visitor asked something
        sentences = _sentences(text, 6)
        if len(sentences) >= 2:
            self.ahead[key] = {"lang": self.lang, "sentences": sentences, "cast": [i.id for i in cast],
                               "facts": {i.id: tuple(i.facts) for i in cast}}
            log.info("story written ahead for %s in %.0f s", key, time.monotonic() - started)
