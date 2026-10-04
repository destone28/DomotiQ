# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Who is who, frame after frame.

Observations are matched to the tracks of the previous frame (Hungarian
assignment on distance and colour), and each track is matched to the
registered identities by its colour signature. Identities are unique: two
tracks cannot be the same character, so the identity assignment is solved as
a whole, and a track that has been confirmed (by registration, by voice or
by a tap in the web app) keeps its identity as long as it is followed.

Figurines of the same colour are told apart only by following them. When
the house loses the thread (they touched, a hand took one), the track goes
back to "uncertain" and the house asks.

A visitor's hand is a large blob coming from the edge: whatever disappears
under it is "carried", keeps its identity and reappears where the hand
leaves it. Figurines do not move by themselves, so the engine tells the
tracker when something new may appear (where a hand has just been) and when
the house is "frozen" (a hand at work, the light of the hall changing):
then nothing is born and nothing disappears. A track already followed that
is not seen for a moment (hidden by a light, touching another figurine)
stays where it was instead of leaving and coming back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..model import ANIMALS, CAR, OBJECT, PERSON, Identity, Track, new_id
from .assignment import linear_sum_assignment
from .geometry import Calibration
from .pipeline import Observation
from .signature import blend, distance, to_hex

MAX_JUMP_MM = 90.0          # farther than this between frames: not the same thing
LOST_S = 1.5                # a young track unseen for longer was noise
YOUNG_S = 2.5               # ...young: followed for less than this, with no identity
HIDDEN_S = 120.0            # a track followed for longer stays where it was, unseen, up to this
CARRIED_GONE_S = 2.5        # carried and not put down this long after the hands left: out of the house
CARRIED_MAX_S = 120.0       # carried this long, hands or not: dropped
ID_ACCEPT = 0.30            # colour distance under which an identity is recognized
ID_MARGIN = 0.07            # the second best must be this much worse
CONFIRM_FRAMES = 2          # frames of agreement before an identity is given
UNKNOWN_ASK_S = 2.0         # in sight this long and recognized as nobody: the house asks who it is


@dataclass
class VTrack:
    id: str
    x: float
    y: float
    obs: Observation | None
    sig: np.ndarray
    category: str = OBJECT
    identity: str | None = None
    locked: bool = False            # confirmed by someone: kept while followed
    confidence: float = 0.0
    uncertain: bool = False
    candidates: list[str] = field(default_factory=list)
    carried: bool = False
    carried_since: float = 0.0
    last_seen: float = field(default_factory=time.time)
    since: float = field(default_factory=time.time)
    hits: int = 0
    votes: dict[str, int] = field(default_factory=dict)
    vx: float = 0.0
    vy: float = 0.0
    moving: bool = False
    history: list[tuple[float, float, float]] = field(default_factory=list)
    asked: float = float("-inf")

    def to_track(self, layout, previous_room: str | None) -> Track:
        room = layout.locate(self.x, self.y, previous_room)
        return Track(self.id, self.x, self.y, self.category, self.identity, room, to_hex(self.sig),
                     round(self.confidence, 2), self.uncertain, list(self.candidates), self.carried,
                     self.moving, self.since)


class Tracker:
    def __init__(self, layout, calib: Calibration) -> None:
        self.layout = layout
        self.calib = calib
        self.tracks: dict[str, VTrack] = {}
        self.hands: list[Observation] = []
        self.identities: dict[str, Identity] = {}
        self._rooms: dict[str, str] = {}
        self.on_question = None          # callback(track, candidates): ask who this is

    def set_identities(self, identities: list[Identity]) -> None:
        self.identities = {i.id: i for i in identities}
        for t in self.tracks.values():
            if t.identity and t.identity not in self.identities:
                t.identity, t.locked, t.confidence = None, False, 0.0

    # ------------------------------------------------------------ update
    def update(self, observations: list[Observation], now: float | None = None, frozen: bool = False,
               quiet_s: float = float("inf")) -> list[Track]:
        """`frozen`: a hand at work or the light changing, nothing is born or lost; `quiet_s`: seconds since
        the last hand. An observation may start a new track only if its extra["birth"] allows it."""
        now = time.time() if now is None else now
        hands = [o for o in observations if o.hand]
        things = [o for o in observations if not o.hand]
        self.hands = hands
        self._associate(things, now, births=not frozen)
        self._carry(hands, now)
        self._drop_lost(now, frozen, quiet_s)
        self._recognize(now)
        self._ask_unknown(now)
        out = []
        for t in self.tracks.values():
            if t.hits < 2 and not t.identity:
                continue                   # a blob seen once may be noise
            tr = t.to_track(self.layout, self._rooms.get(t.id))
            self._rooms[t.id] = tr.room
            out.append(tr)
        return out

    def _position(self, o: Observation, category: str | None) -> tuple[float, float]:
        return o.position(self.calib, category)

    def _associate(self, things: list[Observation], now: float, births: bool = True) -> None:
        """One assignment for all: the tracks in sight by position and colour, the carried ones by colour."""
        tracks = list(self.tracks.values())
        for t in tracks:
            t.obs = None
        matched: set[int] = set()
        if tracks and things:
            cost = np.full((len(tracks), len(things)), 1e6)
            for i, t in enumerate(tracks):
                for j, o in enumerate(things):
                    sd = distance(t.sig, o.sig)
                    if t.carried:
                        # put down somewhere: only the colour tells, and a track in sight is preferred
                        if sd < 0.45:
                            cost[i, j] = 0.8 + 1.5 * sd
                        continue
                    unseen = min(now - t.last_seen, 1.0)
                    dt = min(unseen, 0.5)
                    x, y = self._position(o, t.category)
                    d = float(np.hypot(x - t.x - t.vx * dt, y - t.y - t.vy * dt))
                    if d > MAX_JUMP_MM * (1 + 2 * unseen) or (sd > 0.6 and d > 25):
                        continue
                    cost[i, j] = d / MAX_JUMP_MM + 1.5 * sd
            rows, cols = linear_sum_assignment(cost)
            for i, j in zip(rows, cols):
                if cost[i, j] >= 1e6:
                    continue
                t, o = tracks[i], things[j]
                if t.carried:
                    t.carried = False
                    t.x, t.y = self._position(o, t.category)
                    t.vx = t.vy = 0.0
                    self._apply(t, o, now)
                    # same-colour characters may have been swapped by the hand
                    if t.identity and self._twins(t):
                        self._doubt(t, now)
                else:
                    self._apply(t, o, now)
                o.extra["track"] = t.id
                matched.add(j)
        for j, o in enumerate(things):
            if j in matched or not births or not o.extra.get("birth", True):
                continue
            t = VTrack(new_id("t"), *self._position(o, o.category_guess), o, o.sig, o.category_guess,
                       last_seen=now, since=now)
            self.tracks[t.id] = t
            self._apply(t, o, now)
            o.extra["track"] = t.id

    def _apply(self, t: VTrack, o: Observation, now: float) -> None:
        x, y = self._position(o, t.category)
        dt = max(now - t.last_seen, 1e-3)
        if t.hits:
            vx, vy = (x - t.x) / dt, (y - t.y) / dt
            t.vx, t.vy = 0.6 * t.vx + 0.4 * vx, 0.6 * t.vy + 0.4 * vy
            # a little smoothing on still figurines, none when they move
            speed = float(np.hypot(t.vx, t.vy))
            t.moving = speed > 15.0
            k = 0.85 if t.moving else 0.45
            x, y = t.x + k * (x - t.x), t.y + k * (y - t.y)
        t.x, t.y = x, y
        t.obs = o
        t.last_seen = now
        t.hits += 1
        t.sig = blend(t.sig, o.sig, 0.15 if t.hits > 3 else 0.5)
        if not t.identity and t.category == OBJECT and o.category_guess != OBJECT and t.hits < 20:
            t.category = o.category_guess
        t.history.append((now, x, y))
        if len(t.history) > 50:
            del t.history[:10]

    def _carry(self, hands: list[Observation], now: float) -> None:
        """A track that vanished under a hand is carried, not gone."""
        for t in self.tracks.values():
            if t.obs is not None or t.carried:
                continue
            for h in hands:
                x0, y0 = h.centroid_mm
                # the hand blob covers the object in the image: test in the image
                px = self.calib.image_of(np.array([[t.x, t.y]]), 20.0)[0]
                bx, by, bw, bh = h.bbox
                if bx - 8 <= px[0] <= bx + bw + 8 and by - 8 <= px[1] <= by + bh + 8:
                    t.carried, t.carried_since = True, now
                    t.moving = True
                    break

    def _drop_lost(self, now: float, frozen: bool = False, quiet_s: float = float("inf")) -> None:
        for tid, t in list(self.tracks.items()):
            if t.carried:
                # the hands left without putting it down: taken out of the house
                gone = not frozen and quiet_s > CARRIED_GONE_S and now - t.carried_since > CARRIED_GONE_S
                if gone or now - t.carried_since > CARRIED_MAX_S:
                    del self.tracks[tid]
                    self._rooms.pop(tid, None)
                continue
            unseen = now - t.last_seen
            if unseen <= LOST_S or frozen:
                continue
            young = t.last_seen - t.since < YOUNG_S and not t.identity and not t.locked
            if young or unseen > HIDDEN_S:
                del self.tracks[tid]
                self._rooms.pop(tid, None)

    # ------------------------------------------------------------ identities
    def _twins(self, t: VTrack) -> bool:
        """Other registered identities that look the same as this one."""
        me = self.identities.get(t.identity or "")
        if not me or len(me.signature) == 0:
            return False
        return any(o.id != me.id and len(o.signature) and distance(me.signature, o.signature) < ID_ACCEPT
                   for o in self.identities.values())

    def _doubt(self, t: VTrack, now: float) -> None:
        t.locked = False
        t.uncertain = True
        me = self.identities.get(t.identity or "")
        t.candidates = [o.id for o in self.identities.values()
                        if me and len(o.signature) and distance(me.signature, o.signature) < ID_ACCEPT]
        self._ask(t, now)

    def _ask(self, t: VTrack, now: float) -> None:
        if self.on_question and now - t.asked > 30 and t.candidates:
            t.asked = now
            self.on_question(t, list(t.candidates))

    def assign(self, track_id: str, identity: str | None) -> None:
        t = self.tracks.get(track_id)
        if not t:
            return
        if identity:
            for other in self.tracks.values():
                if other is not t and other.identity == identity:
                    other.identity, other.locked, other.confidence = None, False, 0.0
                    other.votes.clear()
        t.identity = identity
        t.locked = bool(identity)
        t.uncertain = False
        t.candidates = []
        t.confidence = 1.0 if identity else 0.0
        ident = self.identities.get(identity or "")
        if ident:
            t.category = ident.category

    def forget(self, identity: str) -> None:
        for t in self.tracks.values():
            if t.identity == identity:
                t.identity, t.locked, t.confidence = None, False, 0.0
        self.identities.pop(identity, None)

    def _recognize(self, now: float) -> None:
        ids = [i for i in self.identities.values() if len(i.signature)]
        visible = [t for t in self.tracks.values() if t.obs is not None or t.carried]
        locked = {t.identity for t in visible if t.locked and t.identity}
        # a character hidden for a moment is still in its place: its name is not free for another track
        locked |= {t.identity for t in self.tracks.values() if t.obs is None and not t.carried and t.identity}
        free_ids = [i for i in ids if i.id not in locked]
        free_tracks = [t for t in visible if not t.locked and not t.carried and t.hits >= 2]
        if not free_tracks:
            return
        if not free_ids:
            for t in free_tracks:
                t.identity, t.confidence, t.uncertain, t.candidates = None, 0.0, False, []
            return
        cost = np.ones((len(free_tracks), len(free_ids)))
        for i, t in enumerate(free_tracks):
            for j, ident in enumerate(free_ids):
                d = distance(t.sig, ident.signature)
                if ident.category == CAR and t.obs is not None and t.obs.area_mm2 < 2500:
                    d += 0.3                  # the car is much bigger than a figurine
                if ident.category != CAR and t.obs is not None and t.obs.area_mm2 > 7000:
                    d += 0.3
                cost[i, j] = d
        rows, cols = linear_sum_assignment(cost)
        best_of = {i: j for i, j in zip(rows, cols)}
        for i, t in enumerate(free_tracks):
            j = best_of.get(i)
            d = cost[i, j] if j is not None else 1.0
            close = [free_ids[k].id for k in np.argsort(cost[i]) if cost[i, k] < ID_ACCEPT]
            if j is None or d >= ID_ACCEPT:
                t.identity, t.confidence, t.uncertain, t.candidates = None, 0.0, False, []
                t.votes.clear()
                continue
            ident = free_ids[j]
            others = sorted(cost[i, k] for k in range(len(free_ids)) if k != j)
            margin = (others[0] - d) if others else 1.0
            conf = max(0.0, min(1.0, (ID_ACCEPT - d) / ID_ACCEPT * 0.6 + min(margin, 0.3) / 0.3 * 0.4))
            t.votes[ident.id] = t.votes.get(ident.id, 0) + 1
            for k in list(t.votes):
                if k != ident.id:
                    t.votes[k] = max(0, t.votes[k] - 1)
            if t.votes[ident.id] < CONFIRM_FRAMES and t.identity != ident.id:
                continue
            ambiguous = margin < ID_MARGIN and len(close) > 1
            if ambiguous and t.identity != ident.id:
                # two registered characters look the same: follow, but do not guess
                t.identity, t.uncertain, t.candidates, t.confidence = ident.id, True, close, conf
                self._ask(t, now)
                continue
            t.identity, t.confidence = ident.id, conf
            t.category = ident.category
            if not ambiguous:
                t.uncertain, t.candidates = False, []

    def _ask_unknown(self, now: float) -> None:
        """In sight for a while and recognized as nobody: ask who it is. The registered characters that are
        not in the house are proposed, closest colours first, then those whose colours the house has not
        learned yet (the answer teaches them)."""
        if not self.on_question:
            return
        held = {t.identity for t in self.tracks.values() if t.identity}
        free = [i for i in self.identities.values() if i.id not in held]
        if not free:
            return
        for t in self.tracks.values():
            if t.identity or t.obs is None or t.carried or t.asked >= t.since or now - t.since < UNKNOWN_ASK_S \
                    or t.hits < 8:
                continue
            if any(v > 0 for v in t.votes.values()):
                continue                       # being recognized right now
            car = t.obs.area_mm2 > 6000
            fit = [i for i in free if (i.category == CAR) == car]
            trained = sorted((i for i in fit if len(i.signature)), key=lambda i: distance(t.sig, i.signature))
            cands = [i.id for i in trained[:3] + [i for i in fit if not len(i.signature)]][:4]
            if cands:
                t.asked = now
                self.on_question(t, cands)

    # ------------------------------------------------------------ queries
    def track(self, track_id: str) -> VTrack | None:
        return self.tracks.get(track_id)

    def category_of(self, t: VTrack) -> str:
        if t.identity and t.identity in self.identities:
            return self.identities[t.identity].category
        return t.category if t.category in (PERSON, CAR) or t.category in ANIMALS else OBJECT
