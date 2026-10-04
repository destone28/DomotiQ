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
from .pipeline import Observation, surfaces
from .signature import blend, distance, to_hex

MAX_JUMP_MM = 90.0          # farther than this between frames: not the same thing
LOST_S = 1.5                # a young track unseen for longer was noise
YOUNG_S = 2.5               # ...young: followed for less than this, with no identity
HIDDEN_S = 120.0            # a track followed for longer stays where it was, unseen, up to this
HIDDEN_KNOWN_S = 900.0      # ...a known character (behind another one it touches) much longer: it moves only by hand
CARRIED_GONE_S = 2.5        # carried and not put down this long after the hands left: out of the house
CARRIED_MAX_S = 120.0       # carried this long, hands or not: dropped
ID_ACCEPT = 0.30            # colour distance under which an identity is recognized
ID_MARGIN = 0.07            # the second best must be this much worse
CONFIRM_FRAMES = 2          # frames of agreement before an identity is given
UNKNOWN_ASK_S = 1.0         # in sight this long and recognized as nobody: the house asks who it is
NEW_S, NEW_HITS = 1.0, 6    # something new is told to the house once it has stood this long: a reflection
                            # of the arm that has just left lasts less
# Figurines are moved by hand: with no hand around they stand still. Measured on casa1, the middle of the blob
# of a figurine standing still moves 0.3-0.4 mm from a frame to the next (2 mm at most); a reflection or a
# flickering LED jumps by 4-11 mm, or vanishes and comes back. Something that jumps more than JITTER_MM, or
# blinks, at least JITTER_COUNT times within JITTER_WINDOW_S, with no hand around and no animated light in
# its room, is no figurine.
JITTER_MM = 4.0
JITTER_WINDOW_S = 1.5
JITTER_COUNT = 3
SUPPRESS_S, SUPPRESS_MM = 30.0, 25.0   # where one was found, nothing new is born for a while
# Something new is told to the house only when it is surely there, twice: its presence (0-1: seen in almost every
# frame, still, standing out from the floor, compact) over the threshold, and again CHECK_GAP_S later with nothing
# below it in between. In a room where somebody has just said there was nothing, for DOUBT_S, the bar is higher.
PRESENCE_MIN, CHECK_GAP_S = 0.8, 1.0
PRESENCE_DOUBTED, CHECK_GAP_DOUBTED_S, DOUBT_S = 0.92, 2.5, 120.0
HIDDEN_FLAG_S = 1.0         # not seen for longer: told to the house as hidden
ON_FRAMES = 3               # frames on the same piece of furniture before the house is told
# A character lying down, or on the bed, does not look quite as when it was registered: much closer to it than to
# anybody else is enough, after a few more frames
ID_ACCEPT_LOOSE, ID_MARGIN_LOOSE, CONFIRM_LOOSE = 0.45, 0.15, 4
LOOSE_WINDOW_S = 10.0       # ...but only in the first seconds of a track (just put down, or at a start): something
                            # seen for a while does not take a name that has just become free elsewhere
KEEP_MISSES = 8             # a track keeps its name until it fails to look like it for this many frames in a row
# Size as well as colour: the car is never a figurine, nor a figurine the car; and a size very different from the
# one learned (more than SIZE_FREE times, a figurine lying down is three times one standing) counts as less alike
CAR_MIN_MM2, FIGURINE_MAX_MM2 = 2500.0, 6000.0
SIZE_FREE, SIZE_WEIGHT = 2.5, 0.2
CARRIED_SIG = 0.45          # put down: coloured like it
PUT_DOWN_SIG = 0.7          # ...or the one new thing the hands left, even looking a little different (lying down)
FROZEN_JUMP_MM = 30.0       # a figurine stays where it is unless a hand carries it: farther is another blob (with a
                            # hand at work: the hand took it, and it is carried), however long it was unseen
HAND_RECENT_S = 3.6         # for this long after the last hand a figurine may stand somewhere else (pushed, put down)
PLACE_MM = 40.0             # who stood here before: an unknown thing this close to where a character was last seen
FRAGMENT_MM = 40.0          # an unknown blob this close to a character, coloured like it, is a piece of it
MERGED_GROWTH = 0.5         # a figurine put down against another: their blobs are one, bigger by at least half
                            # of the figurine (standing, seen from above, it is small next to one lying down)
MERGED_SIG = 0.9            # ...and coloured partly like it


def _group(category: str | None) -> str:
    """Cars, animals, objects and persons: what can be proposed for what."""
    if category == CAR or category == OBJECT:
        return category
    return "animal" if category in ANIMALS else PERSON


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
    asked: float = float("-inf")          # when the house last asked about two look-alikes
    asked_new: float = float("-inf")      # when it asked who this newcomer is
    raw: tuple[float, float] | None = None   # the middle of its blob in the last frame, before any smoothing
    jumps: list[float] = field(default_factory=list)   # when it jumped with no hand around
    shown: bool = False                    # already told to the house
    frame: int = 0                         # the last frame it was seen in
    born: int = 0                          # the frame it was first seen in
    area: float = 0.0                      # how big its blob usually is, measured with no hand around
    on: str | None = None                  # the furniture it stands on
    on_next: str | None = None             # ...what it seems to stand on now, and for how many frames
    on_frames: int = 0
    misses: int = 0                        # frames in a row it did not look like the character it is named after
    presence: float = 0.0
    checked_at: float = 0.0                # when its presence was first over the threshold

    def to_track(self, layout, previous_room: str | None) -> Track:
        room = layout.locate(self.x, self.y, previous_room)
        return Track(self.id, self.x, self.y, self.category, self.identity, room, to_hex(self.sig),
                     round(self.confidence, 2), self.uncertain, list(self.candidates), self.carried,
                     self.moving, self.since)


class Tracker:
    def __init__(self, layout, calib: Calibration) -> None:
        self.layout = layout
        self.calib = calib
        self.tops = surfaces(layout)          # the bed, the sofa, the tables: figurines stand on them too
        self.tracks: dict[str, VTrack] = {}
        self.hands: list[Observation] = []
        self.identities: dict[str, Identity] = {}
        self._rooms: dict[str, str] = {}
        self.on_question = None          # callback(track, candidates): ask who this is
        self._frozen = False
        self._animated: set[str] = set()                      # rooms whose light is animated now
        self._suppressed: list[tuple[float, float, float]] = []  # (x, y, until): no births there
        self._doubted: dict[str, float] = {}  # room -> until when something new there must be surer
        self.jittery = 0                 # false presences found by their jumps (for the diagnostics)
        self.frame = 0
        self._quiet_s = float("inf")
        # the history: where each character was last seen, and whether a hand has been over that place since
        self.places: dict[str, tuple[float, float, float]] = {}
        self._touched: set[str] = set()

    def set_identities(self, identities: list[Identity]) -> None:
        self.identities = {i.id: i for i in identities}
        for t in self.tracks.values():
            if t.identity and t.identity not in self.identities:
                t.identity, t.locked, t.confidence = None, False, 0.0

    # ------------------------------------------------------------ update
    def update(self, observations: list[Observation], now: float | None = None, frozen: bool = False,
               quiet_s: float = float("inf"), animated: set[str] | None = None) -> list[Track]:
        """`frozen`: a hand at work or the light changing, nothing is born or lost; `quiet_s`: seconds since
        the last hand; `animated`: rooms whose light is animated (a party). An observation may start a new
        track only if its extra["birth"] allows it."""
        now = time.time() if now is None else now
        self._frozen = frozen
        self._quiet_s = quiet_s
        self.frame += 1
        if animated is not None:
            self._animated = set(animated)
        self._suppressed = [s for s in self._suppressed if s[2] > now]
        hands = [o for o in observations if o.hand]
        things = [o for o in observations if not o.hand]
        self.hands = hands
        self._associate(things, now, births=not frozen)
        self._carry(hands, now)
        self._remember(hands, now)
        self._drop_jittery(now)
        self._drop_fragments()
        self._drop_lost(now, frozen, quiet_s)
        self._recognize(now)
        self._ask_unknown(now)
        out = []
        for t in self.tracks.values():
            if not t.shown and not t.identity and not self._confirmed(t, now):
                continue                   # not yet: it may be a reflection, or noise
            t.shown = True
            tr = t.to_track(self.layout, self._rooms.get(t.id))
            tr.hidden = now - t.last_seen > HIDDEN_FLAG_S
            tr.on = t.on
            tr.presence = round(t.presence if not t.identity else 1.0, 2)
            self._rooms[t.id] = tr.room
            out.append(tr)
        return out

    def presence(self, t: VTrack, now: float) -> float:
        """How sure the house is that something is really there, 0-1."""
        o = t.obs
        if o is None:
            return 0.0
        seen = t.hits / max(1, self.frame - t.born + 1)
        f_seen = min(1.0, max(0.0, (seen - 0.5) / 0.45))
        jumps = sum(1 for j in t.jumps if now - j <= JITTER_WINDOW_S)
        f_still = min(1.0, max(0.0, 1.0 - jumps / JITTER_COUNT))
        chroma_d, light_d = o.extra.get("contrast", (0.0, 0.0))
        f_contrast = min(1.0, max(chroma_d / 30.0, -light_d / 25.0, light_d / 40.0, 0.0) / 0.6)
        longest = 6.5 if chroma_d >= 20.0 or light_d <= -15.0 else 3.5     # lying down, if the colour is vivid
        f_shape = 1.0 if o.area_mm2 >= 6000 else min(1.0, max(0.0, (longest + 0.5 - o.elongation) / 1.5))
        return f_seen * f_still * f_contrast * f_shape

    def _confirmed(self, t: VTrack, now: float) -> bool:
        """The double check before something new is told to the house."""
        if t.hits < NEW_HITS or now - t.since < NEW_S or any(now - j < NEW_S for j in t.jumps):
            t.checked_at = 0.0
            return False
        t.presence = self.presence(t, now)
        doubted = self._doubted.get(self.layout.locate(t.x, t.y) or "", 0.0) > now
        need, gap = (PRESENCE_DOUBTED, CHECK_GAP_DOUBTED_S) if doubted else (PRESENCE_MIN, CHECK_GAP_S)
        if t.presence < need:
            t.checked_at = 0.0
            return False
        if not t.checked_at:
            t.checked_at = now                 # first check passed
            return False
        return now - t.checked_at >= gap       # and the second

    @staticmethod
    def _unlike(sig: np.ndarray, area: float, ident: Identity) -> float:
        """How different something looks from a registered identity: colour first, then size."""
        if area and (ident.category == CAR) != (area >= CAR_MIN_MM2) and \
                (ident.category == CAR or area > FIGURINE_MAX_MM2):
            return 1e6                        # the car for a figurine, a figurine for the car
        d = distance(sig, ident.signature)
        if area and ident.size:
            d += SIZE_WEIGHT * max(0.0, abs(float(np.log(area / ident.size))) - float(np.log(SIZE_FREE)))
        return d

    def recognizable(self, sig: np.ndarray, area: float = 0.0) -> bool:
        """Looks like a registered character (closely, or much more than like anybody else)."""
        ds = sorted(self._unlike(sig, area, i) for i in self.identities.values() if len(i.signature))
        if not ds:
            return False
        return ds[0] < ID_ACCEPT or ds[0] < ID_ACCEPT_LOOSE and (len(ds) == 1 or ds[1] - ds[0] >= ID_MARGIN_LOOSE)

    def _position(self, o: Observation, category: str | None) -> tuple[float, float]:
        return o.position(self.calib, category, self.tops)

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
                        # put down somewhere: only the colour tells, and a track in sight is preferred. Only
                        # once the hands have left and where they were: under an arm, a piece of it would do
                        # (or never moved, the hand only passed over it: "place", not "birth")
                        if births and o.extra.get("place", o.extra.get("birth", True)) and sd < CARRIED_SIG:
                            cost[i, j] = 0.8 + 1.5 * sd
                        continue
                    unseen = min(now - t.last_seen, 1.0)
                    dt = min(unseen, 0.5)
                    x, y = self._position(o, t.category)
                    d = float(np.hypot(x - t.x - t.vx * dt, y - t.y - t.vy * dt))
                    if d > MAX_JUMP_MM * (1 + 2 * unseen) or (sd > 0.6 and d > 25):
                        continue
                    if d > FROZEN_JUMP_MM and (self._frozen or self._quiet_s > HAND_RECENT_S or unseen < 0.5):
                        continue          # nothing jumps by itself: farther is another blob
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
                    t.raw, t.jumps = None, []
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
            if self.suppressed(*self._position(o, o.category_guess), now):
                continue
            t = VTrack(new_id("t"), *self._position(o, o.category_guess), o, o.sig, o.category_guess,
                       last_seen=now, since=now, born=self.frame)
            self.tracks[t.id] = t
            self._apply(t, o, now)
            o.extra["track"] = t.id

    def _apply(self, t: VTrack, o: Observation, now: float) -> None:
        x, y = self._position(o, t.category)
        cx, cy = o.centroid_mm
        if t.raw is not None and not self._frozen and (np.hypot(cx - t.raw[0], cy - t.raw[1]) > JITTER_MM
                                                       or self.frame - t.frame > 1) \
                and self.layout.locate(cx, cy) not in self._animated:
            t.jumps.append(now)            # jumped, or seen again after a frame without it
        t.raw, t.frame = (cx, cy), self.frame
        fid = o.standing_on(self.calib, self.tops)[1] if t.category != CAR and o.area_mm2 < 6000 else None
        t.on_frames = t.on_frames + 1 if fid == t.on_next else 1
        t.on_next = fid
        if t.on_frames >= ON_FRAMES:
            t.on = fid                     # three frames alike: no flicker on the edge of the bed
        if t.jumps and now - t.jumps[0] > JITTER_WINDOW_S:
            t.jumps = [j for j in t.jumps if now - j <= JITTER_WINDOW_S]
        dt = max(now - t.last_seen, 1e-3)
        if t.hits:
            vx, vy = (x - t.x) / dt, (y - t.y) / dt
            t.vx, t.vy = 0.6 * t.vx + 0.4 * vx, 0.6 * t.vy + 0.4 * vy
            # a little smoothing on still figurines, none when they move
            speed = float(np.hypot(t.vx, t.vy))
            t.moving = speed > 15.0
            k = 0.85 if t.moving else 0.45
            x, y = t.x + k * (x - t.x), t.y + k * (y - t.y)
        # nothing moves by itself: once it has settled, a figurine keeps its place on the map until a hand has been
        # around (a shadow or a changing light on its blob does not move it)
        if not (t.hits < NEW_HITS or now - t.since < NEW_S or self._frozen or self._quiet_s <= HAND_RECENT_S):
            x, y = t.x, t.y
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
        if self._quiet_s > 5.0:
            t.area = o.area_mm2 if not t.area else 0.8 * t.area + 0.2 * o.area_mm2

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

    def _drop_fragments(self) -> None:
        """A figurine lying across something (a tree trunk, the edge of the bed) can be seen as two blobs: the
        unknown one next to a known character and coloured like it is a piece of that character, not someone
        new to ask about."""
        named = [u for u in self.tracks.values() if u.identity and u.identity in self.identities and not u.carried]
        for tid, t in list(self.tracks.items()):
            if t.identity or t.carried or t.locked or t.obs is None:
                continue
            for u in named:
                if np.hypot(u.x - t.x, u.y - t.y) < FRAGMENT_MM and \
                        distance(t.sig, self.identities[u.identity].signature) < ID_ACCEPT:
                    del self.tracks[tid]
                    self._rooms.pop(tid, None)
                    break

    def _remember(self, hands: list[Observation], now: float) -> None:
        """Keep the history of where each character was; a hand over a place may have taken what stood there."""
        for t in self.tracks.values():
            if t.identity and t.obs is not None and not t.carried:
                self.places[t.identity] = (t.x, t.y, now)
                self._touched.discard(t.identity)
        if not hands:
            return
        held = {t.identity for t in self.tracks.values() if t.identity}
        for ident, (x, y, _) in self.places.items():
            if ident in held or ident in self._touched:
                continue
            px = self.calib.image_of(np.array([[x, y]]), 20.0)[0]
            for h in hands:
                bx, by, bw, bh = h.bbox
                if bx - 8 <= px[0] <= bx + bw + 8 and by - 8 <= px[1] <= by + bh + 8:
                    self._touched.add(ident)
                    break

    def was_here(self, t: VTrack) -> str | None:
        """The character that stood right here, now not in sight anywhere, with no hand over its place since:
        it is still that one (nothing moves by itself), seen again or seen differently."""
        held = {u.identity for u in self.tracks.values() if u.identity and u is not t}
        best, dist = None, PLACE_MM
        for ident, (x, y, _) in self.places.items():
            if ident in held or ident in self._touched or ident not in self.identities:
                continue
            d = float(np.hypot(t.x - x, t.y - y))
            if d < dist:
                best, dist = ident, d
        return best

    def dismiss(self, track_id: str, now: float) -> tuple[float, float] | None:
        """Nothing there, somebody said: the track goes and nothing is born there for a while. Returns the middle
        of what was seen (where the engine forgets it)."""
        t = self.tracks.pop(track_id, None)
        if t is None:
            return None
        self._rooms.pop(track_id, None)
        self._suppressed.append((t.x, t.y, now + SUPPRESS_S))
        self._doubt(t, now)
        return t.raw or (t.x, t.y)

    def _doubt(self, t: VTrack, now: float) -> None:
        """Nothing was there: in that room something new must be surer for a while."""
        room = self.layout.locate(t.x, t.y)
        if room:
            self._doubted[room] = now + DOUBT_S

    def _put_down_as(self, t: VTrack) -> bool:
        """The hands took a character and left something new, not recognized: nothing moves by itself, so it is
        that character, lying down or on the bed looking a little different. With more new things, the one
        coloured most like it."""
        if not t.identity:
            return False
        new = [u for u in self.tracks.values() if u is not t and not u.identity and not u.carried
               and u.obs is not None and u.since >= t.carried_since - 0.5]
        best = min(new, key=lambda u: distance(t.sig, u.obs.sig), default=None)
        if best is None or (len(new) > 1 and distance(t.sig, best.obs.sig) >= PUT_DOWN_SIG):
            return False
        best.identity, best.locked, best.confidence = t.identity, t.locked, max(t.confidence, 0.5)
        best.category, best.shown, best.misses = t.category, True, 0
        best.votes = {t.identity: CONFIRM_LOOSE}
        return True

    def _put_against(self, t: VTrack, now: float) -> bool:
        """A carried figurine that was not seen put down: if a blob grew as much as a figurine and is coloured
        partly like it, the two touch. It stays there, hidden behind the other, until they part."""
        best, growth = None, 0.0
        for u in self.tracks.values():
            if u is t or u.carried or u.obs is None or distance(t.sig, u.obs.sig) >= MERGED_SIG:
                continue
            # grown since before the hands came by at least half of this figurine, or (just put down too)
            # bigger than this figurine alone by as much
            size = t.area or 300.0
            grown = u.obs.area_mm2 - (u.area if u.area else size)
            g = grown / (MERGED_GROWTH * size)
            if g >= 1.0 and g > growth:
                best, growth = u, g
        if best is None:
            return False
        t.carried = False
        t.x, t.y, t.vx, t.vy = best.x, best.y, 0.0, 0.0
        t.raw, t.jumps = None, []
        t.last_seen = now
        return True

    def suppressed(self, x: float, y: float, now: float) -> bool:
        return any(until > now and np.hypot(x - sx, y - sy) < SUPPRESS_MM for sx, sy, until in self._suppressed)

    def _jittery(self, t: VTrack, now: float) -> bool:
        if t.carried or self._frozen:
            return False
        return sum(1 for j in t.jumps if now - j <= JITTER_WINDOW_S) >= JITTER_COUNT

    def _drop_jittery(self, now: float) -> None:
        """Something unknown that keeps jumping with no hand around is a reflection or a flickering light:
        it goes, nothing is born where it was for a while, and its blob joins the empty house as any change
        with no hand does. A character the house knows is only hidden while it shakes."""
        for tid, t in list(self.tracks.items()):
            if t.identity or t.locked or t.obs is None or not self._jittery(t, now):
                continue
            del self.tracks[tid]
            self._rooms.pop(tid, None)
            self._suppressed.append((t.x, t.y, now + SUPPRESS_S))
            self._doubt(t, now)
            t.obs.extra.pop("track", None)
            self.jittery += 1

    def _drop_lost(self, now: float, frozen: bool = False, quiet_s: float = float("inf")) -> None:
        for tid, t in list(self.tracks.items()):
            if t.carried:
                # the hands left without putting it down: taken out of the house, unless it was put down against
                # another figurine and the two are seen as one
                gone = not frozen and quiet_s > CARRIED_GONE_S and now - t.carried_since > CARRIED_GONE_S
                if gone and (self._put_down_as(t) or self._put_against(t, now)):
                    if t.carried:
                        del self.tracks[tid]       # its name went to what the hands put down
                        self._rooms.pop(tid, None)
                    continue
                if gone or now - t.carried_since > CARRIED_MAX_S:
                    del self.tracks[tid]
                    self._rooms.pop(tid, None)
                continue
            unseen = now - t.last_seen
            if unseen <= LOST_S or frozen:
                continue
            # never told to the house, or followed only for a moment: it was noise
            young = (t.last_seen - t.since < YOUNG_S or not t.shown) and not t.identity and not t.locked
            if young or unseen > (HIDDEN_KNOWN_S if t.identity else HIDDEN_S):
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
        """Names for the tracks in sight that are not confirmed. A name is never in two places: one held by a
        track (confirmed, hidden for a moment, in a hand, or recognized) goes to another track only after its
        holder has stopped looking like it for KEEP_MISSES frames; so a character touching another one, unseen,
        does not lend its name to some blob elsewhere."""
        ids = [i for i in self.identities.values() if len(i.signature)]
        visible = [t for t in self.tracks.values() if t.obs is not None or t.carried]
        free_tracks = [t for t in visible if not t.locked and not t.carried and t.hits >= 2]
        if not free_tracks:
            return
        taken = {t.identity for t in self.tracks.values() if t.identity and t not in free_tracks}
        cands = [i for i in ids if i.id not in taken]
        raw = np.ones((len(free_tracks), max(len(cands), 1)))     # how much it looks like each one
        for i, t in enumerate(free_tracks):
            for j, ident in enumerate(cands):
                raw[i, j] = self._unlike(t.sig, t.obs.area_mm2 if t.obs is not None else 0.0, ident)
        cost = raw.copy()
        for i, t in enumerate(free_tracks):
            for j, ident in enumerate(cands):
                if any(u.identity == ident.id for u in free_tracks if u is not t):
                    cost[i, j] = 1e6          # held by another track in sight
        best_of = dict(zip(*linear_sum_assignment(cost))) if cands else {}
        for i, t in enumerate(free_tracks):
            j = best_of.get(i)
            d = cost[i, j] if j is not None else 1.0
            if d >= 1e6:
                j, d = None, 1.0
            # twins are told by how much it looks like each of them, whoever holds the name
            others = sorted(raw[i, k] for k in range(len(cands)) if k != j) if j is not None else []
            margin = (others[0] - d) if others else 1.0
            loose = d >= ID_ACCEPT
            fits = j is not None and d < ID_ACCEPT_LOOSE and not (loose and margin < ID_MARGIN_LOOSE)
            if fits and t.identity != cands[j].id and loose and now - t.since > LOOSE_WINDOW_S:
                fits = False                  # too late for a loose name: only a close match now
            if not fits:
                if t.identity:
                    t.misses += 1
                    if t.misses < KEEP_MISSES:
                        continue              # keeps its name for a moment (a shadow, a hand nearby)
                t.identity, t.confidence, t.uncertain, t.candidates = None, 0.0, False, []
                t.votes.clear()
                t.misses = 0
                continue
            t.misses = 0
            ident = cands[j]
            close = [cands[k].id for k in np.argsort(raw[i]) if raw[i, k] < ID_ACCEPT]
            conf = max(0.0, min(1.0, (ID_ACCEPT - d) / ID_ACCEPT * 0.6 + min(margin, 0.3) / 0.3 * 0.4))
            t.votes[ident.id] = t.votes.get(ident.id, 0) + 1
            for k in list(t.votes):
                if k != ident.id:
                    t.votes[k] = max(0, t.votes[k] - 1)
            if t.votes[ident.id] < (CONFIRM_LOOSE if loose else CONFIRM_FRAMES) and t.identity != ident.id:
                continue
            ambiguous = margin < ID_MARGIN and len(close) > 1
            if ambiguous and t.identity != ident.id:
                # two registered characters look the same: follow, but do not guess
                t.identity, t.uncertain, t.candidates, t.confidence = ident.id, True, close, conf
                self._ask(t, now)
                continue
            t.identity, t.confidence = ident.id, conf
            t.category = ident.category
            # the same character still "in a hand": it was put down here
            for tid in [k for k, c in self.tracks.items() if c is not t and c.carried and c.identity == ident.id]:
                del self.tracks[tid]
                self._rooms.pop(tid, None)
            if not ambiguous:
                t.uncertain, t.candidates = False, []

    def adopt(self, o: Observation, now: float) -> None:
        """A new track for something that stands out and stays, though no hand was seen putting it down."""
        if self.suppressed(*self._position(o, o.category_guess), now):
            return
        t = VTrack(new_id("t"), *self._position(o, o.category_guess), o, o.sig, o.category_guess,
                   last_seen=now, since=now, born=self.frame)
        self.tracks[t.id] = t
        self._apply(t, o, now)
        o.extra["track"] = t.id

    def _ask_unknown(self, now: float) -> None:
        """In sight for a while and recognized as nobody: ask who it is. The registered characters that are
        not in the house are proposed, closest colours first, then those whose colours the house has not
        learned yet (the answer teaches them)."""
        if not self.on_question:
            return
        held = {t.identity for t in self.tracks.values() if t.identity}
        free = [i for i in self.identities.values() if i.id not in held]
        for t in self.tracks.values():
            if t.identity or t.obs is None or t.carried or t.asked_new >= t.since or now - t.since < UNKNOWN_ASK_S \
                    or t.hits < NEW_HITS or not t.shown:
                continue                       # asked only about what the house is sure is there
            if any(v > 0 for v in t.votes.values()):
                continue                       # being recognized right now
            before = self.was_here(t)
            if before is not None:
                # no hand has been here since that character stood here: it is that one, nothing to ask
                self.assign(t.id, before)
                t.locked = False
                continue
            # proposed by kind: cars for a car, animals for an animal, objects for an object; a new person is
            # asked the name (a registered name said aloud or typed is recognized anyway)
            kind = CAR if t.obs.area_mm2 > 6000 or t.category == CAR else _group(t.category)
            fit = [] if kind == PERSON else [i for i in free if _group(i.category) == kind]
            trained = sorted((i for i in fit if len(i.signature)), key=lambda i: distance(t.sig, i.signature))
            cands = [i.id for i in trained[:3] + [i for i in fit if not len(i.signature)]][:4]
            # asked even with no candidate: the answer may be a new name
            t.asked_new = now
            self.on_question(t, cands)

    # ------------------------------------------------------------ queries
    def track(self, track_id: str) -> VTrack | None:
        return self.tracks.get(track_id)

    def category_of(self, t: VTrack) -> str:
        if t.identity and t.identity in self.identities:
            return self.identities[t.identity].category
        return t.category if t.category in (PERSON, CAR) or t.category in ANIMALS else OBJECT
