# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The language model that understands free sentences.

Qwen2.5-0.5B-Instruct runs in llama-server (llama.cpp) as its own service.
It never writes what the house says: it only chooses an intent and its
arguments, and its output is constrained by a JSON schema, so it cannot
answer anything but one of the intents below. The answer is then composed
from the real state of the house, which is why it cannot invent facts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from typing import Iterable

from .intents import Intent

log = logging.getLogger(__name__)

URL = "http://127.0.0.1:8081"

INTENTS = ["where_is", "who_in", "count", "temperature", "humidity", "time_now", "lights_on",
           "lights_off", "scene", "party", "grill", "grill_stop", "car_where", "house_summary", "help",
           "language", "volume", "who_are_you", "register", "other"]
ROOMS = ["kitchen", "living", "bedroom", "bathroom", "utility", "garage", "garden", "driveway", "house"]
COLORS = ["red", "green", "blue", "yellow", "orange", "purple", "pink", "white", "cyan", "warm"]
SCENES = ["normal", "cinema", "relax", "night", "away"]

SYSTEM = """You map what a visitor says to a smart home (a 1:20 diorama) onto one intent.
Rooms: kitchen, living (living room/soggiorno), bedroom (camera), bathroom (bagno), utility (locale tecnico), garage, garden (giardino), driveway (vialetto).
Intents:
- where_is(name): where a character is
- who_in(room): who is in a room
- count(room): how many people
- temperature(room), humidity(room)
- time_now
- lights_on(room, color), lights_off(room)
- scene(scene): normal, cinema, relax, night, away
- party, grill, grill_stop
- car_where
- house_summary: how the house is, what is happening
- help: what the house can do
- language(language): it or en
- volume(direction): up or down
- who_are_you, register (add a new character)
- other: anything not about the house
Known characters: {names}.
The sentence can be in Italian or English and may contain recognition errors.
Answer only with the JSON object."""

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "name": {"type": "string"},
        "room": {"type": "string", "enum": ROOMS},
        "color": {"type": "string", "enum": COLORS},
        "scene": {"type": "string", "enum": SCENES},
        "language": {"type": "string", "enum": ["it", "en"]},
        "direction": {"type": "string", "enum": ["up", "down"]},
    },
    "required": ["intent"],
}


class LanguageModel:
    def __init__(self, url: str = URL, timeout: float = 15.0) -> None:
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

    def _ask(self, sentence: str, names: list[str]) -> dict:
        body = {
            "messages": [
                {"role": "system", "content": SYSTEM.format(names=", ".join(names) or "none")},
                {"role": "user", "content": sentence},
            ],
            "temperature": 0,
            "max_tokens": 60,
            "response_format": {"type": "json_object", "schema": SCHEMA},
        }
        req = urllib.request.Request(self.url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read())
        return json.loads(out["choices"][0]["message"]["content"])

    async def understand(self, sentence: str, names: Iterable[str]) -> Intent | None:
        names = list(names)
        try:
            data = await asyncio.get_running_loop().run_in_executor(None, self._ask, sentence, names)
            self.ok = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            log.info("language model not available: %s", e)
            self.ok = False
            return None
        intent = data.get("intent")
        if intent not in INTENTS or intent == "other":
            return Intent("other", {}, 0.5, "llm")
        args = {k: data[k] for k in ("name", "room", "color", "scene", "language", "direction")
                if data.get(k)}
        if "name" in args and args["name"] not in names:
            # the model may spell a name its own way: keep it only if it is a known one
            from .intents import find_name
            fixed = find_name(args["name"].lower(), names, 0.7)
            if fixed:
                args["name"] = fixed
            else:
                args.pop("name")
        if args.get("room") == "house":
            args.pop("room")
        return Intent(intent, args, 0.7, "llm")
