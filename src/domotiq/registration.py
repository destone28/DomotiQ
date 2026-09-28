# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Registering a new character, pet, car or object.

Whoever starts it (a phone, the intercom, a voice command) gives a name; the
house then looks for something it sees but does not know. With exactly one
candidate it takes it; with several it asks which one; with none it waits
for the figurine to be put down. The category is guessed (from the photo if
there is one, otherwise from the size seen from above) and confirmed.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .identities import NameTaken, clean_name
from .model import CATEGORIES, CATEGORY_NAMES, PERSON, Identity, new_id

if TYPE_CHECKING:
    from .app import Context

SESSION_S = 150.0


@dataclass
class Session:
    id: str
    name: str
    origin: str = "web"                  # web | intercom | voice
    photo: str | None = None
    status: str = "waiting"              # waiting | choose | confirm | done | cancelled | expired
    candidates: list[str] = field(default_factory=list)
    track: str | None = None
    room: str | None = None
    category_guess: str | None = None
    label_guess: str | None = None       # e.g. "chair" from the photo classifier
    identity: str | None = None
    device: str | None = None
    nickname: str | None = None
    message: str | None = None
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Registration:
    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        self.sessions: dict[str, Session] = {}
        self.on_update: list[Callable[[Session], None]] = []
        ctx.bus.subscribe("tracks_changed", lambda e: self.poll())

    # ------------------------------------------------------------ helpers
    def _unknown(self, room: str | None = None) -> list[str]:
        busy = {s.track for s in self.sessions.values() if s.track and s.status in ("confirm",)}
        out = []
        for t in self.ctx.house.tracks.values():
            if t.identity or t.carried or t.id in busy:
                continue
            if room and t.room != room:
                continue
            out.append(t.id)
        return out

    def _publish(self, s: Session) -> None:
        self.ctx.bus.publish("registration", **s.to_dict())
        for cb in self.on_update:
            cb(s)

    # ------------------------------------------------------------ flow
    def start(self, name: str, *, origin: str = "web", photo: str | None = None,
              room: str | None = None, category: str | None = None,
              device: str | None = None, nickname: str | None = None) -> Session:
        name = clean_name(name)
        if not name:
            raise ValueError("empty name")
        existing = self.ctx.identities.by_name(name)
        if existing:
            raise NameTaken(name, existing)
        s = Session(new_id("reg"), name, origin, photo, room=room, device=device, nickname=nickname)
        if category in CATEGORIES:
            s.category_guess = category
        if photo and self.ctx.classifier is not None:
            guess = self.ctx.classifier.classify_file(photo)
            if guess:
                s.category_guess = s.category_guess or guess[0]
                s.label_guess = guess[1]
        self.sessions[s.id] = s
        self._advance(s)
        return s

    def _advance(self, s: Session) -> None:
        if s.status not in ("waiting", "choose"):
            return
        cands = self._unknown(s.room)
        if len(cands) == 1:
            self._take(s, cands[0])
        elif len(cands) > 1:
            if s.status != "choose" or set(cands) != set(s.candidates):
                s.status, s.candidates = "choose", cands
                self._publish(s)
        elif s.status == "choose":
            s.status, s.candidates = "waiting", []
            self._publish(s)
        else:
            self._publish(s)

    def _take(self, s: Session, track_id: str) -> None:
        track = self.ctx.house.tracks.get(track_id)
        if not track:
            return
        s.track = track_id
        s.room = track.room
        s.candidates = []
        s.category_guess = s.category_guess or self.ctx.vision.category_guess(track_id) or \
            (track.category if track.category in CATEGORIES and track.category != "object" else None) or PERSON
        s.status = "confirm"
        self._publish(s)

    def pick(self, sid: str, track_id: str) -> Session:
        s = self.sessions[sid]
        if track_id not in self._unknown():
            raise ValueError("that object is not free any more")
        self._take(s, track_id)
        return s

    def confirm(self, sid: str, category: str | None = None) -> Identity:
        s = self.sessions[sid]
        if s.status != "confirm" or not s.track:
            raise ValueError("nothing to confirm yet")
        category = category if category in CATEGORIES else (s.category_guess or PERSON)
        track = self.ctx.house.tracks.get(s.track)
        sig = self.ctx.vision.signature(s.track) if track and not track.virtual else None
        color = sig[1] if sig else (track.color if track else "#888888")
        ident = self.ctx.identities.add(s.name, category, color=color, signature=sig[0] if sig else None,
                                        photo=s.photo, device=s.device, nickname=s.nickname)
        if track and track.virtual:
            obj = self.ctx.sim.objects.get(track.id)
            if obj:
                obj.identity, obj.category, obj.name = ident.id, category, ident.name
        else:
            self.ctx.vision.assign(s.track, ident.id)
        if track:
            track.identity, track.category = ident.id, category
        s.identity, s.status = ident.id, "done"
        self._publish(s)
        self.ctx.bus.publish("registered", identity=ident.id, name=ident.name, category=category,
                             origin=s.origin, room=s.room)
        self.sessions.pop(sid, None)
        return ident

    def cancel(self, sid: str) -> None:
        s = self.sessions.pop(sid, None)
        if s:
            s.status = "cancelled"
            self._publish(s)

    def poll(self) -> None:
        now = time.time()
        for s in list(self.sessions.values()):
            if now - s.created > SESSION_S:
                s.status = "expired"
                self.sessions.pop(s.id, None)
                self._publish(s)
                continue
            if s.status in ("waiting", "choose"):
                self._advance(s)
            elif s.status == "confirm" and s.track not in self.ctx.house.tracks:
                s.status, s.track = "waiting", None
                self._advance(s)

    def category_label(self, category: str, lang: str) -> str:
        return CATEGORY_NAMES.get(category, {}).get(lang, category)

    def list(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.sessions.values()]
