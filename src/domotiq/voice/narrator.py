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
with the character), and each is said in one of several ways (variants.py).

On the bed or the sofa the house says so ("Ecco Viola sul letto della
camera!"); on a table, a bench, the fridge and the other furniture it tells
the character to get down at once.

What it has said about a character it does not say again while that
character stays where it was (a figurine seen again after a shadow, its
name found again, the edge of the bed): only a real move is news. A move
from one room to another always is; coming into sight, going out of it or
getting on a piece of furniture in the same room is not, when it was said
less than ten minutes before (a figurine at the edge of the picture comes
and goes, and would be told to get off the same furniture every minute).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from . import answers
from . import variants as V

if TYPE_CHECKING:
    from .manager import Voice

SETTLE_S = 1.2           # a move is told once the character has stayed this long in its new room
STALE_S = 12.0           # a line that could not be said for this long is dropped
MAX_LINES = 3            # said together at most
REPEAT_S = 600.0         # a character still where the house last said it is is not told again for this long
OUTSIDE = ("outside", "driveway", None)


class Narrator:
    def __init__(self, voice: "Voice") -> None:
        self.voice = voice
        self.ctx = voice.ctx
        self._moves: dict[str, dict[str, Any]] = {}      # track -> the move waiting to settle
        self._lines: list[tuple[float, str, dict[str, str]]] = []   # (when, track, line)
        self._hushed: set[str] = set()     # newcomers just named aloud: the dialogue already said it
        self._told: dict[str, tuple[tuple, float]] = {}    # name -> ((room, furniture) last said, when)
        self._history: dict[str, dict[tuple, float]] = {}  # name -> {(room, furniture) said: when}
        bus = self.ctx.bus
        bus.subscribe("room_enter", self._on_enter)
        bus.subscribe("room_exit", self._on_exit)
        bus.subscribe("identity_changed", self._on_identity)
        bus.subscribe("car", self._on_car)
        bus.subscribe("furniture", self._on_furniture)

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
                              "name": ev.get("name"), "category": ev.get("category"), "identity": ev.get("identity")}

    def hush(self, track: str | None) -> None:
        """The newcomer of this track has just been named in a dialogue: no "Ecco Marco!" after it."""
        if track:
            self._hushed.add(track)

    def _on_identity(self, ev) -> None:
        """Somebody said who a newcomer is, or the house recognized it late: now it can be named."""
        track, name = ev.get("track"), ev.get("name")
        if track in self._hushed:
            self._hushed.discard(track)
            return
        if not track or not name or ev.get("before"):
            return
        t = self.ctx.house.tracks.get(track)
        if t is None or t.carried:
            return
        self._moves[track] = {"from": None, "to": t.room, "at": time.monotonic() - SETTLE_S, "name": name,
                              "category": t.category}

    def _on_car(self, ev) -> None:
        if ev.get("state") == "parked":
            it, en = V.pick("car.parked", V.CAR_PARKED)
            self._add(f"car:{ev.get('track')}", {"it": it, "en": en})

    def _on_furniture(self, ev) -> None:
        """Up on a piece of furniture (or down from it) without changing room."""
        track, name = ev.get("track"), ev.get("name")
        if not track or not name or track in self._moves and self._moves[track].get("to") is not None:
            return                                     # a newcomer, or a move that will say it when it settles
        if not ev.get("on"):
            self._moves.pop(track, None)
            return
        self._moves[track] = {"from": ev.get("room"), "to": ev.get("room"), "at": time.monotonic(), "name": name,
                              "category": ev.get("category"), "furniture": True}

    # ------------------------------------------------------------ lines
    def line(self, move: dict[str, Any], on: str | None = None) -> dict[str, str] | None:
        """The words for a settled move (`on`: the furniture it stands on now), or None when there is nothing
        worth saying."""
        name, src, dst = move.get("name"), move.get("from"), move.get("to")
        if not name:
            return None                                # newcomers are asked about, not announced
        ctx = self.ctx
        if dst is not None and on:
            item = answers.furniture(ctx, on)
            if item:
                if item.get("rest"):                   # the bed, the sofa
                    return self._said("rest", V.REST, name=name, on_it=item["on"]["it"], on_en=item["on"]["en"])
                return self._said("off", V.GET_OFF, name=name, off_it=item["off"]["it"], off_en=item["off"]["en"])
        if src == dst:
            return None
        if dst is None:
            return self._said("leave", V.LEAVE, name=name)
        where_it, where_en = answers.room(ctx, dst, "it"), answers.room(ctx, dst, "en")
        if src is None:
            return self._said("arrive", V.ARRIVE, name=name, where_it=where_it, where_en=where_en)
        if src in OUTSIDE and dst not in OUTSIDE:
            return self._said("enter", V.ENTER, name=name)
        if dst == "driveway" and src not in OUTSIDE:
            return self._said("driveway", V.TO_DRIVEWAY, name=name)
        to_en = where_en.replace("in the ", "to the ", 1).replace("on the ", "to the ", 1)
        return self._said("move", V.MOVE, name=name, where_it=where_it, where_en=to_en)

    @staticmethod
    def _said(key: str, table: list, name: str, **values: str) -> dict[str, str]:
        it_values = {k[:-3]: v for k, v in values.items() if k.endswith("_it")}
        en_values = {k[:-3]: v for k, v in values.items() if k.endswith("_en")}
        en_values = {("to" if k == "where" else k): v for k, v in en_values.items()} | \
            ({"where": values["where_en"]} if "where_en" in values else {})
        it, en = V.said_each(f"narrator.{key}", table, {"name": name, **it_values}, {"name": name, **en_values})
        return {"it": it, "en": en}

    def _again(self, name: str | None, where: tuple, now: float, moved: bool = True) -> bool:
        """Already said, a moment ago: this character, in this room and on this furniture (the last thing said
        about it, or, when it did not move from one room to another, anything said in the last REPEAT_S).
        Otherwise it is news, and remembered."""
        if not name:
            return False
        last = self._told.get(name)
        if last is not None and last[0] == where and now - last[1] < REPEAT_S:
            return True
        said = self._history.setdefault(name, {})
        if not moved and now - said.get(where, float("-inf")) < REPEAT_S:
            return True
        self._told[name] = (where, now)
        said[where] = now
        return False

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
                if move.get("to") is None and move.get("identity") and \
                        self.ctx.house.where_is(move["identity"]) is not None:
                    continue                           # still in the house (put down elsewhere): no goodbye
                t = self.ctx.house.tracks.get(track)
                on = t.on if t is not None and move.get("to") is not None else None
                line = self.line(move, on)
                moved = move.get("from") not in OUTSIDE and move.get("to") not in OUTSIDE and \
                    move.get("from") != move.get("to")
                if line and not self._again(move.get("name"), (move.get("to"), on), now, moved):
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
