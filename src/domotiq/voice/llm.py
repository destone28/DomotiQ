# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The language model that understands free sentences.

Qwen2.5-0.5B-Instruct runs in llama-server (llama.cpp) as its own service.
It never writes what the house says: it only chooses an intent and its
arguments, and a grammar forces its output to be one of them, written in a
few words ("who_in kitchen", "where_is Marco", "other"). The answer is then
composed from the real state of the house, which is why it cannot invent
facts.

On the board the model reads about 11 tokens per second and writes about 6,
so everything is kept short: the instructions and the examples are always
the same text at the start of the conversation, which llama-server keeps in
its cache, and each request adds only the sentence and the known names.

The same model also tells what an answer to "who is it?" means (who.py),
whether an answer accepts an offer of the house (offers.py), and what a
question about a character is about when no keyword does (facts.py). Each of
these instructions stays in a slot of llama-server of its own (-np 4), so no
kind of request pushes another out of the cache. With fewer slots the topics
share the slot of "who is it?", and llama-server keeps the prompt it takes out
of a slot in its memory cache (--cache-ram, on by default).

Reading the instructions takes the board about ten minutes, after every start
of llama-server. Once read, each slot is saved to a file of llama-server
(--slot-save-path), and at the next start it is put back from there in a
moment.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import threading
import time
import urllib.request
from collections import OrderedDict
from typing import Callable, Iterable

from . import facts, offers, who
from .intents import Intent, find_name, find_room

log = logging.getLogger(__name__)

URL = "http://127.0.0.1:8081"
COMMANDS_SLOT, ANSWERS_SLOT, OFFERS_SLOT, FACTS_SLOT = 0, 1, 2, 3   # each kind of request in a slot of its own
ANSWER_TIMEOUT_S = 12.0                 # the instructions not read yet (just started): the house asks again
READ_S = 5.0                            # instructions that took longer than this were read, not put back: saved

ROOMS = ["kitchen", "living", "bedroom", "bathroom", "utility", "garage", "garden", "driveway", "house"]
COLORS = ["red", "green", "blue", "yellow", "orange", "purple", "pink", "white", "cyan", "warm"]
SCENES = ["normal", "cinema", "relax", "night", "away"]
# intent: the arguments it takes, in order
FORMS = {
    "where_is": ["name"], "who_in": ["room"], "count": ["room"], "temperature": ["room"], "humidity": ["room"],
    "time_now": [], "lights_on": ["room", "color"], "lights_off": ["room"], "scene": ["scene"], "party": [],
    "grill": [], "grill_stop": [], "car_where": [], "house_summary": [], "help": [], "language": ["language"],
    "volume": ["direction"], "who_are_you": [], "register": [], "joke": [], "other": [],
}
INTENTS = list(FORMS)

SYSTEM = """You control a model smart home. Turn what the visitor says into one command of the house.
Rooms: kitchen, living (living room, soggiorno, salotto), bedroom (camera da letto), bathroom (bagno), utility (locale tecnico), garage, garden (giardino), driveway (vialetto), house (the whole house).
Commands: where_is NAME, who_in ROOM, count ROOM, temperature ROOM, humidity ROOM, time_now, lights_on ROOM COLOR, lights_off ROOM, scene normal|cinema|relax|night|away, party, grill, grill_stop, car_where, house_summary, help, language it|en, volume up|down, who_are_you, register, joke, other.
Use other for anything that is not about this house: weather, news, sport, general knowledge, chit-chat.
Sentences may be in Italian or English and may contain recognition errors."""

# examples given as a conversation: a small model follows them much better than a description.
# They are mixed in a fixed order (a small model tends to repeat the last answers it saw) and
# never change, so llama-server keeps them in its cache.
_EXAMPLES = [
    ("dov'è finito Marco", "where_is Marco"), ("where is Leo", "where_is Leo"),
    ("chi c'è in cucina adesso", "who_in kitchen"), ("is anybody in the bedroom", "who_in bedroom"),
    ("quante persone ci sono in soggiorno", "count living"), ("how many people are in the garden", "count garden"),
    ("fa freddo qui dentro", "temperature house"), ("how hot is it in the kitchen", "temperature kitchen"),
    ("com'è l'umidità del bagno", "humidity bathroom"), ("is the bathroom humid", "humidity bathroom"),
    ("che ore sono", "time_now"), ("tell me the time", "time_now"),
    ("metti una luce viola in camera", "lights_on bedroom purple"), ("make the garden green", "lights_on garden green"),
    ("spegni la luce in cucina", "lights_off kitchen"), ("turn off the garage lights", "lights_off garage"),
    ("vorrei un po' di atmosfera romantica", "scene relax"), ("guardiamo un film", "scene cinema"),
    ("spegni tutto che vado a dormire", "scene night"), ("we are all going out", "scene away"),
    ("facciamo festa", "party"), ("put on some music and dance", "party"),
    ("light the barbecue", "grill"), ("accendi la griglia", "grill"),
    ("spegni il barbecue", "grill_stop"),
    ("where did I park the car", "car_where"), ("la macchina è in garage?", "car_where"),
    ("cosa sta succedendo in casa", "house_summary"), ("give me a report of the house", "house_summary"),
    ("what can you do", "help"), ("come funzioni", "help"),
    ("parla inglese", "language en"), ("speak italian", "language it"),
    ("alza la voce", "volume up"), ("quieter please", "volume down"),
    ("chi sei tu", "who_are_you"), ("voglio aggiungere un personaggio nuovo", "register"),
    ("raccontami una barzelletta", "joke"), ("make me laugh", "joke"),
    ("che tempo fa domani a Milano", "other"), ("chi ha vinto la partita ieri", "other"),
    ("what is the capital of France", "other"), ("ciao come stai", "other"), ("quanto fa sette per otto", "other"),
    ("Marco ha pagato le bollette", "other"), ("quando scade l'assicurazione della macchina", "other"),
    ("did Leo feed the cat this morning", "other"),
]


def _mixed(examples: list[tuple[str, str]]) -> list[tuple[str, str]]:
    import random
    out = list(examples)
    random.Random(3).shuffle(out)
    while out[-1][1] == "other":
        out.insert(0, out.pop())
    return out


EXAMPLES = _mixed(_EXAMPLES)
EXAMPLE_NAMES = "Marco, Sofia, Leo"
MIN_CONFIDENCE = 0.35      # below this the first word of the command was a guess


def _user(names: str, sentence: str) -> str:
    return f"Names: {names}. Sentence: {sentence}"


def messages(sentence: str, names: list[str]) -> list[dict[str, str]]:
    out = [{"role": "system", "content": SYSTEM}]
    for said, command in EXAMPLES:
        out.append({"role": "user", "content": _user(EXAMPLE_NAMES, said)})
        out.append({"role": "assistant", "content": command})
    out.append({"role": "user", "content": _user(", ".join(names) if names else "none", sentence)})
    return out


def grammar(names: list[str]) -> str:
    """GBNF: exactly one command, in the form above."""
    def alt(words):
        return " | ".join(json.dumps(w) for w in words)
    name_words = [n for n in names if n and '"' not in n] or ["nobody"]
    rules = [
        f'root ::= {" | ".join(_form(i) for i in INTENTS)}',
        f"room ::= {alt(ROOMS)}",
        f"color ::= {alt(COLORS)}",
        f"scene ::= {alt(SCENES)}",
        f"name ::= {alt(name_words + ['unknown'])}",
        'language ::= "it" | "en"',
        'direction ::= "up" | "down"',
    ]
    return "\n".join(rules)


def _form(intent: str) -> str:
    parts = [json.dumps(intent)] + [f'" " {arg}' for arg in FORMS[intent]]
    return "(" + " ".join(parts) + ")"


def parse_command(text: str, names: list[str]) -> Intent | None:
    words = text.strip().split()
    if not words or words[0] not in FORMS:
        return None
    intent = words[0]
    if intent == "other":
        return Intent("other", {}, 0.5, "llm")
    args = {}
    rest = words[1:]
    for arg in FORMS[intent]:
        if not rest:
            break
        if arg == "name":
            # names may have more than one word: the rest of the line
            value = " ".join(rest)
            rest = []
            if value == "unknown":
                continue
            fixed = value if value in names else find_name(value.lower(), names, 0.7)
            if fixed:
                args["name"] = fixed
            continue
        value = rest.pop(0)
        if arg == "room" and value == "house":
            continue
        args[arg] = value
    return Intent(intent, args, 0.7, "llm")


MEMO_SIZE = 256         # requests whose answer is kept: the same sentence again is answered at once


class LanguageModel:
    def __init__(self, url: str = URL, timeout: float = 20.0) -> None:
        self.url = url
        self.timeout = timeout
        self._answers: OrderedDict[tuple, tuple[str, float]] = OrderedDict()
        self._answers_lock = threading.Lock()
        self.ok = False
        self.slots = 0          # slots of llama-server: the answers to offers need the third one
        self.model = ""         # the model file of llama-server: the saved slots are of that model only
        self.cold = False       # llama-server started again since the instructions went in: its cache is empty

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=2) as r:
                self.ok = r.status == 200
        except OSError:
            self.ok = False
        if self.ok:
            self.slots = self._slots()
            self.cold = self._cold()
        return self.ok

    def _slots(self) -> int:
        try:
            with urllib.request.urlopen(self.url + "/props", timeout=2) as r:
                props = json.loads(r.read())
            self.model = str(props.get("model_path") or "")
            return int(props.get("total_slots") or 0)
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def _cold(self) -> bool:
        """The slot of the commands holds no instructions: llama-server has just started (again)."""
        try:
            with urllib.request.urlopen(self.url + "/slots", timeout=2) as r:
                slots = json.loads(r.read())
            first = next((s for s in slots if s.get("id") == COMMANDS_SLOT), {})
            return int(first.get("n_prompt_tokens") or 0) < 100
        except (OSError, ValueError, TypeError, AttributeError):
            return False        # no list of the slots: taken as ready, as before

    @property
    def facts_slot(self) -> int:
        """The topics have a slot of their own with four; with fewer they share the one of "who is it?"."""
        return FACTS_SLOT if self.slots > FACTS_SLOT else ANSWERS_SLOT

    def _memo(self, key: tuple, call: Callable[[], tuple[str, float]]) -> tuple[str, float]:
        """What the model answered to this very request: with temperature 0 it would answer the same, after seconds
        on the board. Otherwise it is asked, and the answer kept (the last MEMO_SIZE)."""
        with self._answers_lock:
            hit = self._answers.get(key)
            if hit is not None:
                self._answers.move_to_end(key)
                return hit
        out = call()
        with self._answers_lock:
            self._answers[key] = out
            while len(self._answers) > MEMO_SIZE:
                self._answers.popitem(last=False)
        return out

    def remembers(self, sentence: str, names: Iterable[str]) -> bool:
        """This command was asked already: its answer comes at once (no "Let me see...")."""
        with self._answers_lock:
            return _command_key(sentence, list(names)) in self._answers

    def _ask(self, sentence: str, names: list[str], timeout: float | None = None) -> tuple[str, float]:
        """The command, and how sure the model was of its first word (0..1)."""
        return self._chat(messages(sentence, names), grammar(names), COMMANDS_SLOT, 12, timeout)

    def _classify(self, sentence: str, timeout: float | None = None) -> tuple[str, float]:
        """What kind of answer to "who is it?" the sentence is, as a form of who.GRAMMAR."""
        return self._chat(who.messages(sentence), who.GRAMMAR, ANSWERS_SLOT, 10, timeout)

    def _topic(self, sentence: str, timeout: float | None = None) -> tuple[str, float]:
        """What a sentence about a character is about, as a label of facts.GRAMMAR."""
        return self._chat(facts.messages(sentence), facts.GRAMMAR, self.facts_slot, 6, timeout)

    def _offer(self, question: str, sentence: str, timeout: float | None = None) -> tuple[str, float]:
        """Whether the sentence accepts the offer `question`, as a form of offers.GRAMMAR_GBNF."""
        return self._chat(offers.messages(question, sentence), offers.GRAMMAR_GBNF, OFFERS_SLOT, 4, timeout)

    def _chat(self, msgs: list[dict[str, str]], gbnf: str, slot: int, max_tokens: int,
              timeout: float | None) -> tuple[str, float]:
        body = {
            "messages": msgs,
            "temperature": 0,
            "max_tokens": max_tokens,
            "cache_prompt": True,
            "grammar": gbnf,
            "logprobs": True,
            "top_logprobs": 1,
            "id_slot": slot,
        }
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            out = json.loads(r.read())
        choice = out["choices"][0]
        content = (choice.get("logprobs") or {}).get("content") or []
        confidence = math.exp(content[0]["logprob"]) if content and "logprob" in content[0] else 1.0
        return choice["message"]["content"], confidence

    def warm(self) -> bool:
        """Put the instructions in the cache before the first visitor speaks; False if llama-server answered none.

        Each slot is first put back from the file saved after the last reading (a moment); otherwise, or if the
        instructions changed since, they are read (on the board a few minutes each) and the slot is saved for
        the next start. A slot shared by two instructions is not saved: only one of them could come back.
        """
        sets = [("commands", COMMANDS_SLOT, lambda: self._ask("ciao", [], timeout=600)),
                ("answers", ANSWERS_SLOT, lambda: self._classify("ciao", timeout=600)),
                ("facts", self.facts_slot, lambda: self._topic("ciao", timeout=600))]
        if self.slots > OFFERS_SLOT:
            sets.append(("offers", OFFERS_SLOT, lambda: self._offer("Facciamo festa?", "ciao", timeout=600)))
        answered = False
        for name, slot, ask in sets:
            own = sum(1 for _, other, _ in sets if other == slot) == 1
            restored = own and self._slot_file("restore", slot, name)
            start = time.monotonic()
            try:
                ask()
            except (OSError, ValueError, KeyError):
                continue
            answered = True
            took = time.monotonic() - start
            if own and took > READ_S:
                saved = self._slot_file("save", slot, name)
                log.info("language model: %s instructions read in %.0f s%s", name, took, ", saved" if saved else "")
            elif restored:
                log.info("language model: %s instructions put back from the last start", name)
        return answered

    def _slot_file(self, action: str, slot: int, name: str) -> bool:
        """Save a slot to a file of llama-server (action "save"), or put it back from there ("restore"). False if
        it cannot: no file yet, another model, or llama-server started without --slot-save-path."""
        tag = hashlib.sha1(self.model.encode()).hexdigest()[:8]
        body = json.dumps({"filename": f"domotiq-{name}-{tag}.bin"}).encode()
        req = urllib.request.Request(f"{self.url}/slots/{slot}?action={action}", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status == 200
        except (OSError, ValueError):
            return False

    async def understand(self, sentence: str, names: Iterable[str]) -> Intent | None:
        names = list(names)
        sentence = re.sub(r"\s+", " ", sentence).strip()
        try:
            text, confidence = await asyncio.get_running_loop().run_in_executor(
                None, self._memo, _command_key(sentence, names), lambda: self._ask(sentence, names))
            self.ok = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.info("language model not available: %s", e)
            self.ok = False
            return None
        intent = parse_command(text, names)
        if intent is None:
            log.info("language model answered something else: %r", text)
            return None
        log.info("language model: %r (%.2f)", text, confidence)
        if confidence < MIN_CONFIDENCE and intent.name != "other":
            # a guess: better to say it was not understood than to do the wrong thing
            return Intent("other", {"guess": intent.name}, confidence, "llm")
        # a registered name said with no room is almost always "where is"
        if intent.name in ("who_in", "count", "other", "where_is") and not find_room(_plain(sentence)):
            name = find_name(_plain(sentence), names, 0.85)
            if name:
                return Intent("where_is", {"name": name}, confidence, "llm")
        intent.confidence = confidence
        return intent


    async def classify(self, sentence: str, names: Iterable[str]) -> who.Reply | None:
        """What an answer to "who is it?" means, when the rules of who.py could not tell."""
        names = list(names)
        sentence = re.sub(r"\s+", " ", sentence).strip()
        try:
            text, confidence = await asyncio.get_running_loop().run_in_executor(
                None, self._memo, ("who", sentence.lower()), lambda: self._classify(sentence, ANSWER_TIMEOUT_S))
            self.ok = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.info("language model not available: %s", e)
            return None
        reply = who.parse(text, sentence, names, confidence)
        log.info("language model, answer: %r (%.2f) -> %s", text, confidence, reply)
        return reply

    async def topic(self, sentence: str, least: float = facts.MIN_CONFIDENCE) -> str | None:
        """What a question about a character (or one of its facts) is about, when no keyword tells: a label of
        facts.LABELS, "other" when it is about nothing the facts tell (or the model was less sure than
        `least`), None when the model is not available."""
        sentence = re.sub(r"\s+", " ", sentence).strip()
        try:
            text, confidence = await asyncio.get_running_loop().run_in_executor(
                None, self._memo, ("topic", sentence.lower()), lambda: self._topic(sentence, ANSWER_TIMEOUT_S))
            self.ok = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.info("language model not available: %s", e)
            return None
        topic = facts.parse_topic(text, confidence, least)
        log.info("language model, topic: %r (%.2f) -> %s", text, confidence, topic)
        return topic or "other"

    async def offer_answer(self, question: str, sentence: str) -> offers.Answer | None:
        """Whether an answer accepts an offer, when the rules of offers.py could not tell. None when the model
        cannot be asked: with fewer than three slots these instructions would push out those of the commands."""
        if self.slots <= OFFERS_SLOT:
            return None
        sentence = re.sub(r"\s+", " ", sentence).strip()
        try:
            text, confidence = await asyncio.get_running_loop().run_in_executor(
                None, self._memo, ("offer", question, sentence.lower()),
                lambda: self._offer(question, sentence, ANSWER_TIMEOUT_S))
            self.ok = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.info("language model not available: %s", e)
            return None
        answer = offers.from_model(text, confidence)
        log.info("language model, offer: %r (%.2f) -> %s", text, confidence, answer)
        return answer


def _command_key(sentence: str, names: list[str]) -> tuple:
    return ("command", re.sub(r"\s+", " ", sentence).strip().lower(), tuple(names))


def _plain(text: str) -> str:
    from .intents import normalize
    return normalize(text)
