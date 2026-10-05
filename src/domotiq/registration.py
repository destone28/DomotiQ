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
    label_name: dict[str, str] | None = None   # the proposed name of an object, {"it": "sedia", "en": "chair"}
    warnings: list[dict[str, str]] = field(default_factory=list)   # what may make it hard to recognize
    identity: str | None = None
    device: str | None = None
    nickname: str | None = None
    message: str | None = None
    auto: bool = False                   # voice and intercom: confirmed as soon as the figurine is found
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
              device: str | None = None, nickname: str | None = None,
              track: str | None = None, auto: bool = False, force: bool = False) -> Session:
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
                from .vision.classify import label_name
                s.category_guess = s.category_guess or guess[0]
                s.label_guess = guess[1]
                s.label_name = {"it": label_name(guess[1], "it"), "en": label_name(guess[1], "en")}
        s.auto = auto
        s.warnings = self._vocabulary_warnings(name)
        self.sessions[s.id] = s
        # `force`: that very track, even if the house took it for somebody it was not sure of
        if track and (track in self._unknown() or force and track in self.ctx.house.tracks):
            self._take(s, track)
        else:
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
        s.warnings = [w for w in s.warnings if w.get("kind") == "vocabulary"] + \
            ([] if track.virtual else self.ctx.vision.quality(track_id))
        s.status = "confirm"
        self._publish(s)
        if s.auto:
            # the name was already confirmed by voice; the category can be changed later in the web app
            self.confirm(s.id)

    def _vocabulary_warnings(self, name: str) -> list[dict[str, str]]:
        """A name the speech recognizer does not know can be registered, but not called by voice."""
        voice = self.ctx.voice
        listener = getattr(voice, "listener", None) if voice is not None else None
        if listener is None or not getattr(listener, "ok", False):
            return []
        out = []
        if not listener.known(name, "it"):
            out.append({"kind": "vocabulary", "it": f"Il riconoscimento vocale italiano non conosce «{name}»: "
                        "a voce potrei non capirlo. Scegli un nome più comune, o va bene così per la webapp.",
                        "en": f"The Italian speech recognizer does not know “{name}”: I may not understand it by "
                        "voice. Pick a more common name, or keep it for the web app."})
        if not listener.known(name, "en"):
            out.append({"kind": "vocabulary", "it": f"Il riconoscimento vocale inglese non conosce «{name}»: dopo "
                        "la registrazione puoi scrivere come si pronuncia in inglese nella scheda del personaggio.",
                        "en": f"The English speech recognizer does not know “{name}”: after registering, write "
                        "how it sounds in English in the character's card."})
        return out

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
            self.ctx.house.name(track, ident.id, category)
        s.identity, s.status = ident.id, "done"
        self._publish(s)
        self.ctx.bus.publish("registered", identity=ident.id, name=ident.name, category=category,
                             origin=s.origin, room=s.room)
        self.sessions.pop(sid, None)
        return ident

    def name_track(self, track_id: str, identity: str | None = None, name: str | None = None,
                   category: str | None = None, nickname: str | None = None, device: str | None = None) -> Identity:
        """Somebody says who this presence is, in the web app: one already known (`identity`: the name moves here
        from wherever it was, since a name is never in two places, and this look is learned), or a new one (`name`
        and `category`). Raises KeyError for a presence or a character that is not there, NameTaken for a new name
        that already exists, ValueError for an empty one."""
        ctx = self.ctx
        track = ctx.house.tracks.get(track_id)
        if track is None:
            raise KeyError(track_id)
        if identity:
            ident = ctx.identities.get(identity)
            if ident is None:
                raise KeyError(identity)
        else:
            clean = clean_name(name or "")
            if not clean:
                raise ValueError("empty name")
            existing = ctx.identities.by_name(clean)
            if existing:
                raise NameTaken(clean, existing)
            category = category if category in CATEGORIES else (track.category if track.category in CATEGORIES
                                                                 and track.category != "object" else PERSON)
            sig = ctx.vision.signature(track_id) if not track.virtual else None
            ident = ctx.identities.add(clean, category, color=sig[1] if sig else track.color,
                                       signature=sig[0] if sig else None, device=device, nickname=nickname)
            ctx.bus.publish("registered", identity=ident.id, name=ident.name, category=ident.category,
                            origin="web", room=track.room)
        if track.virtual:
            for obj in ctx.sim.objects.values():
                if obj.identity == ident.id and obj.id != track_id:
                    obj.identity, obj.name = None, ""
            obj = ctx.sim.objects.get(track_id)
            if obj:
                obj.identity, obj.category, obj.name = ident.id, ident.category, ident.name
        else:
            ctx.vision.assign(track_id, ident.id, explicit=True)
        # the house shows it at once, without waiting for the next picture
        before = ctx.house.name(track, ident.id, ident.category)
        for cid, c in list(ctx.house.confirmations.items()):
            if c["context"].get("kind") == "who" and c["context"].get("track") == track_id:
                ctx.house.withdraw(cid)
        ctx.bus.publish("identity_changed", track=track_id, identity=ident.id, name=ident.name, before=before,
                        room=track.room, category=ident.category)
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
