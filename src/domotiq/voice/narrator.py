# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""A few words aloud for what happens in the house.

Every character that comes in, goes out or changes room is told ("Ecco Viola
in soggiorno!", "Viola va in cucina.", "Ciao Viola, a presto!"), and so is
the car parked in the garage (its arrival and departure are said by the
rules). The house waits until a move has settled, so a figurine carried
across a room for a moment is not announced, merges what happens together
in one go, and never talks over a question or while someone speaks to it.
A newcomer the house does not know is not announced: it is asked about.
Every line agrees with any name (no adjective or participle that changes
with the character).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from . import answers

if TYPE_CHECKING:
    from .manager import Voice

SETTLE_S = 1.2           # a move is told once the character has stayed this long in its new room
STALE_S = 12.0           # a line that could not be said for this long is dropped
MAX_LINES = 3            # said together at most
OUTSIDE = ("outside", "driveway", None)


class Narrator:
    def __init__(self, voice: "Voice") -> None:
        self.voice = voice
        self.ctx = voice.ctx
        self._moves: dict[str, dict[str, Any]] = {}      # track -> the move waiting to settle
        self._lines: list[tuple[float, str, dict[str, str]]] = []   # (when, track, line)
        bus = self.ctx.bus
        bus.subscribe("room_enter", self._on_enter)
        bus.subscribe("room_exit", self._on_exit)
        bus.subscribe("identity_changed", self._on_identity)
        bus.subscribe("car", self._on_car)

    # ------------------------------------------------------------ events
    def _on_enter(self, ev) -> None:
        track = ev.get("track")
        if not track:
            return
        move = self._moves.get(track)
        if move is None:
            move = self._moves[track] = {"from": ev.get("other")}
        move.update(to=ev.get("room"), at=time.monotonic(), name=ev.get("name"), category=ev.get("category"))

    def _on_exit(self, ev) -> None:
        track = ev.get("track")
        if not track or ev.get("other") is not None:
            return                                     # a move: the room_enter that follows tells it
        move = self._moves.get(track)
        if move is not None and move.get("from") is None:
            del self._moves[track]                     # came and went before it was told: nothing to say
            return
        self._moves[track] = {"from": ev.get("room"), "to": None, "at": time.monotonic(),
                              "name": ev.get("name"), "category": ev.get("category")}

    def _on_identity(self, ev) -> None:
        """Somebody said who a newcomer is, or the house recognized it late: now it can be named."""
        track, name = ev.get("track"), ev.get("name")
        if not track or not name or ev.get("before"):
            return
        t = self.ctx.house.tracks.get(track)
        if t is None or t.carried:
            return
        self._moves[track] = {"from": None, "to": t.room, "at": time.monotonic() - SETTLE_S, "name": name,
                              "category": t.category}

    def _on_car(self, ev) -> None:
        if ev.get("state") == "parked":
            self._add(f"car:{ev.get('track')}", {"it": "L'auto è parcheggiata in garage.",
                                                 "en": "The car is parked in the garage."})

    # ------------------------------------------------------------ lines
    def line(self, move: dict[str, Any]) -> dict[str, str] | None:
        """The words for a settled move, or None when there is nothing worth saying."""
        name, src, dst = move.get("name"), move.get("from"), move.get("to")
        if not name or src == dst:
            return None                                # newcomers are asked about, not announced
        ctx = self.ctx
        if dst is None:
            return {"it": f"Ciao {name}, a presto!", "en": f"Bye {name}, see you soon!"}
        where_it, where_en = answers.room(ctx, dst, "it"), answers.room(ctx, dst, "en")
        if src is None:
            return {"it": f"Ecco {name} {where_it}!", "en": f"Here's {name} {where_en}!"}
        if src in OUTSIDE and dst not in OUTSIDE:
            return {"it": f"{name} entra in casa.", "en": f"{name} comes into the house."}
        if dst == "driveway" and src not in OUTSIDE:
            return {"it": f"{name} esce sul vialetto.", "en": f"{name} goes out onto the driveway."}
        to_en = where_en.replace("in the ", "to the ", 1).replace("on the ", "to the ", 1)
        return {"it": f"{name} va {where_it}.", "en": f"{name} goes {to_en}."}

    def _add(self, key: str, line: dict[str, str], now: float | None = None) -> None:
        """Queue a line; a newer line about the same character replaces the one not said yet."""
        now = time.monotonic() if now is None else now
        self._lines = [x for x in self._lines if x[1] != key] + [(now, key, line)]

    def _quiet(self) -> bool:
        v = self.voice
        speaking = self.ctx.audio is not None and getattr(self.ctx.audio, "speaking", False)
        return not v.busy.locked() and not v.in_flight and not speaking

    def tick(self, now: float | None = None) -> list[dict[str, str]]:
        """Settle the moves and say what is due; returns the lines said (for the tests)."""
        now = time.monotonic() if now is None else now
        for track, move in list(self._moves.items()):
            if now - move["at"] >= SETTLE_S:
                del self._moves[track]
                line = self.line(move)
                if line:
                    self._add(track, line, now)
        self._lines = [x for x in self._lines if now - x[0] < STALE_S]
        if not self._lines or not self._quiet():
            return []
        batch, self._lines = self._lines[:MAX_LINES], self._lines[MAX_LINES:]
        said = {lang: " ".join(line[lang] for _, _, line in batch) for lang in ("it", "en")}
        self.voice.last_chatter = time.monotonic()          # no chatty question right after it
        self.voice._spawn(self.ctx.actions.say(said))
        return [line for _, _, line in batch]

    async def run(self) -> None:
        while True:
            await asyncio.sleep(0.3)
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the narrator must never stop
                import logging
                logging.getLogger(__name__).exception("narrator")
