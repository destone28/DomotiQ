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
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import urllib.request
from typing import Iterable

from .intents import Intent, find_name, find_room

log = logging.getLogger(__name__)

URL = "http://127.0.0.1:8081"

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


class LanguageModel:
    def __init__(self, url: str = URL, timeout: float = 20.0) -> None:
        self.url = url
        self.timeout = timeout
        self.ok = False

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=2) as r:
                self.ok = r.status == 200
        except OSError:
            self.ok = False
        return self.ok

    def _ask(self, sentence: str, names: list[str], timeout: float | None = None) -> tuple[str, float]:
        """The command, and how sure the model was of its first word (0..1)."""
        body = {
            "messages": messages(sentence, names),
            "temperature": 0,
            "max_tokens": 12,
            "cache_prompt": True,
            "grammar": grammar(names),
            "logprobs": True,
            "top_logprobs": 1,
        }
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            out = json.loads(r.read())
        choice = out["choices"][0]
        content = (choice.get("logprobs") or {}).get("content") or []
        confidence = math.exp(content[0]["logprob"]) if content and "logprob" in content[0] else 1.0
        return choice["message"]["content"], confidence

    def warm(self) -> None:
        """Read the instructions once, so they are in the cache before the first visitor speaks.

        On the board this takes a couple of minutes, once after each start.
        """
        try:
            self._ask("ciao", [], timeout=600)
        except (OSError, ValueError, KeyError):
            pass

    async def understand(self, sentence: str, names: Iterable[str]) -> Intent | None:
        names = list(names)
        sentence = re.sub(r"\s+", " ", sentence).strip()
        try:
            text, confidence = await asyncio.get_running_loop().run_in_executor(None, self._ask, sentence, names)
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


def _plain(text: str) -> str:
    from .intents import normalize
    return normalize(text)
