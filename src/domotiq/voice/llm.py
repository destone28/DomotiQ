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
import re
import urllib.request
from typing import Iterable

from .intents import Intent, find_name

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

SYSTEM = """You understand what visitors say to a model smart home and answer with one command.
Rooms: kitchen, living (living room, soggiorno, salotto), bedroom (camera da letto), bathroom (bagno), utility (locale tecnico), garage, garden (giardino), driveway (vialetto), house (the whole house).
Commands:
where_is NAME - where a character is
who_in ROOM - who is in a room
count ROOM - how many people are there
temperature ROOM / humidity ROOM
time_now - what time it is
lights_on ROOM COLOR / lights_off ROOM
scene normal|cinema|relax|night|away
party / grill / grill_stop / car_where
house_summary - what is happening in the house
help - what the house can do
language it|en / volume up|down
who_are_you / register - a new character wants to join
joke - the visitor wants a joke
other - anything else: weather, news, sport, general knowledge, chit-chat, other places
Sentences may be in Italian or English and may contain recognition errors.
Examples:
dov'è finito Marco => where_is Marco
chi c'è in cucina adesso => who_in kitchen
could you tell me who is hanging out in the kitchen => who_in kitchen
c'è qualcuno in casa => who_in house
quante persone ci sono in soggiorno => count living
fa freddo qui dentro => temperature house
com'è l'umidità del bagno => humidity bathroom
che ore sono => time_now
metti una luce viola in camera => lights_on bedroom purple
vorrei un po' di atmosfera romantica => scene relax
spegni tutto che vado a dormire => scene night
usciamo tutti di casa => scene away
facciamo festa => party
accendi il barbecue => grill
where did I park the car => car_where
cosa sta succedendo in casa => house_summary
what can you do => help
parla inglese => language en
alza la voce => volume up
chi sei tu => who_are_you
voglio aggiungere un personaggio nuovo => register
raccontami una barzelletta => joke
che tempo fa domani a Milano => other
chi ha vinto la partita => other
what is the capital of France => other
quanto fa due più due => other
ciao come stai => other"""


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

    def _ask(self, sentence: str, names: list[str]) -> str:
        known = ", ".join(names) if names else "none"
        body = {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Known names: {known}\n{sentence} =>"},
            ],
            "temperature": 0,
            "max_tokens": 12,
            "cache_prompt": True,
            "grammar": grammar(names),
        }
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read())
        return out["choices"][0]["message"]["content"]

    def warm(self) -> None:
        """Read the instructions once, so they are in the cache before the first visitor speaks."""
        try:
            self._ask("ciao", [])
        except (OSError, ValueError, KeyError):
            pass

    async def understand(self, sentence: str, names: Iterable[str]) -> Intent | None:
        names = list(names)
        sentence = re.sub(r"\s+", " ", sentence).strip()
        try:
            text = await asyncio.get_running_loop().run_in_executor(None, self._ask, sentence, names)
            self.ok = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.info("language model not available: %s", e)
            self.ok = False
            return None
        intent = parse_command(text, names)
        if intent is None:
            log.info("language model answered something else: %r", text)
        return intent
