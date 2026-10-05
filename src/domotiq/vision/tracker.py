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
from typing import Iterable

import numpy as np

from ..model import ANIMALS, CAR, OBJECT, PERSON, Identity, Track, new_id
from .assignment import linear_sum_assignment
from .geometry import Calibration
from .pipeline import Observation, surfaces
from .signature import SIG_LEN, blend, distance, distances, to_hex

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
ON_FRAMES = 5               # frames on the same piece of furniture before the house is told
OFF_FRAMES = 15             # ...and off it: the edge of the bed, a shadow, do not take a figurine down and up again
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
SIZE_ODD = 4.0              # a blob more than this many times bigger or smaller than every look of a character is not it
# The looks of each character, learned on the board: besides its registered colours, up to MAX_POSES poses (lying
# down, on the bed, under another light), each with its colours, size and shape. A pose is added when a character
# the house follows with confidence (or that somebody has just named) looks unlike all the poses it knows.
MAX_POSES, NEW_POSE, POSE_STEADY_S = 6, 0.16, 2.0
ELONG_WEIGHT = 0.04
# A pose shows the same figurine from another side, not another colour: it must be coloured like the character as
# registered, and more like it than like anybody else. A look learned on the wrong blob (the LEDs of a board, another
# character standing close) would make the house see that character everywhere.
POSE_MAX_SIG, POSE_MARGIN = 0.45, 0.05
# a look somebody chose in the web app ("this is Rossellina"): learned even if the light changed it a lot
POSE_TAUGHT_MAX = 0.6
# Names move only with a hand: a character is never recognized this far from where it was last seen, unless a hand
# has been over that place since (or carried it); and a named figurine keeps its name while no hand is around.
PLACE_JUMP_MM = 50.0
SURE_S = 6.0                # something unknown counts for an alarm only after standing there this long
# The car lives in the garage: anywhere else something car-sized is far more often a light, a shadow or figurines
# huddled together. The house asks about a car out of the garage only when it is certain: seen still and clearly
# for this long
CAR_SURE_S, CAR_SURE_PRESENCE = 10.0, 0.95
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
        self.posed: set[str] = set()      # identities with new poses, to be kept by the house
        # every look of every character in one table, so that a blob is compared with all of them at once; and the
        # comparisons of this frame, which several steps ask for
        self._looks_table: tuple | None = None
        self._unlike_memo: dict[int, tuple[np.ndarray, float, float, np.ndarray]] = {}

    def set_identities(self, identities: list[Identity]) -> None:
        self.identities = {i.id: i for i in identities}
        self._looks_changed()
        self._forget_wrong_poses()
        for t in self.tracks.values():
            if t.identity and t.identity not in self.identities:
                t.identity, t.locked, t.confidence = None, False, 0.0

    # ------------------------------------------------------------ looks
    def _looks_changed(self) -> None:
        self._looks_table = None
        self._unlike_memo.clear()

    def _looks(self) -> tuple:
        """(identities in order, signatures of all their looks, owner of each look, sizes, elongations, is a car)."""
        if self._looks_table is None:
            order = list(self.identities.values())
            sigs, owner, sizes, elongs = [], [], [], []
            for k, ident in enumerate(order):
                looks = [(ident.signature, ident.size, 0.0)] + [(p["sig"], p.get("size", 0.0), p.get("elong", 0.0))
                                                                 for p in ident.poses if p.get("sig")]
                for sig, size, elong in looks:
                    if len(sig) == SIG_LEN:
                        sigs.append(sig)
                        owner.append(k)
                        sizes.append(size or 0.0)
                        elongs.append(elong or 0.0)
            self._looks_table = (order, np.asarray(sigs, np.float32).reshape(-1, SIG_LEN), np.asarray(owner, int),
                                 np.asarray(sizes, np.float64), np.asarray(elongs, np.float64),
                                 np.array([i.category == CAR for i in order], bool))
        return self._looks_table

    def _unlike_all(self, sig: np.ndarray, area: float = 0.0, elong: float = 0.0) -> np.ndarray:
        """`_unlike` against every identity at once, in the order of `_looks()[0]`."""
        order, sigs, owner, sizes, elongs, is_car = self._looks()
        memo = self._unlike_memo.get(id(sig))
        if memo is not None and memo[0] is sig and memo[1] == area and memo[2] == elong:
            return memo[3]
        out = np.full(len(order), 1e6)
        if len(sigs) and len(sig) == SIG_LEN:
            d = distances(np.asarray(sig, np.float32), sigs)[0].astype(np.float64)
            if area:
                has = sizes > 0
                d[has] += SIZE_WEIGHT * np.maximum(0.0, np.abs(np.log(area / sizes[has])) - np.log(SIZE_FREE))
            if elong:
                has = elongs > 0
                d[has] += ELONG_WEIGHT * np.abs(elong - elongs[has])
            np.minimum.at(out, owner, d)
            if area:
                out[(is_car != (area >= CAR_MIN_MM2)) & (is_car | (area > FIGURINE_MAX_MM2))] = 1e6
        self._unlike_memo[id(sig)] = (sig, area, elong, out)
        return out

    def _unlike_of(self, sig: np.ndarray, area: float, ident: Identity, elong: float = 0.0) -> float:
        order = self._looks()[0]
        for k, i in enumerate(order):
            if i is ident:
                return float(self._unlike_all(sig, area, elong)[k])
        return self._unlike(sig, area, ident, elong)

    def fits_pose(self, ident: Identity, sig: np.ndarray, limit: float = POSE_MAX_SIG, margin: bool = True) -> bool:
        """Can this look be a pose of this character? Coloured like it as registered (within `limit`), more than like
        anybody else (`margin`; not for a look somebody chose in the web app)."""
        if len(ident.signature) != SIG_LEN or len(sig) != SIG_LEN:
            return False
        own = distance(sig, ident.signature)
        if own > limit:
            return False
        return not margin or not any(o is not ident and len(o.signature) == SIG_LEN and
                                     distance(sig, o.signature) < own + POSE_MARGIN for o in self.identities.values())

    def fits_taught(self, ident: Identity, sig: np.ndarray) -> bool:
        return self.fits_pose(ident, sig, POSE_TAUGHT_MAX, margin=False)

    def _forget_wrong_poses(self) -> None:
        """Poses learned on the wrong blob before this check existed are forgotten (and the house keeps the rest)."""
        for ident in self.identities.values():
            kept = [p for p in ident.poses if p.get("sig") and (
                self.fits_taught if p.get("taught") else self.fits_pose)(ident, np.asarray(p["sig"], np.float32))]
            if len(kept) != len(ident.poses):
                ident.poses = kept
                self.posed.add(ident.id)
                self._looks_changed()

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
        self._settle_doubts(now)
        self._learn_poses(now)
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
            tr.sure = self._sure(t, now)
            self._rooms[t.id] = tr.room
            out.append(tr)
        self._unlike_memo.clear()          # the blobs of the next frame are new ones
        return out

    def _sure(self, t: VTrack, now: float) -> bool:
        """Sure enough for an alarm: a character the house knows (confirmed, or recognized closely), or something
        unknown that has stood there, still and clearly seen, for SURE_S."""
        if t.carried:
            return False
        if t.identity:
            return bool(not t.uncertain and (t.locked or t.confidence >= 0.5))
        return bool(t.shown and now - t.since >= SURE_S and t.presence >= PRESENCE_MIN and
                    not any(now - j <= JITTER_WINDOW_S for j in t.jumps))

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
    def _unlike(sig: np.ndarray, area: float, ident: Identity, elong: float = 0.0) -> float:
        """How different something looks from a registered identity: colour first, then size and shape, against
        the closest of its looks (as registered, and the poses learned since)."""
        if area and (ident.category == CAR) != (area >= CAR_MIN_MM2) and \
                (ident.category == CAR or area > FIGURINE_MAX_MM2):
            return 1e6                        # the car for a figurine, a figurine for the car
        looks = [(ident.signature, ident.size, 0.0)] + [(p["sig"], p.get("size", 0.0), p.get("elong", 0.0))
                                                         for p in ident.poses if p.get("sig")]
        looks = [lk for lk in looks if len(lk[0]) == SIG_LEN]
        if not looks or len(sig) != SIG_LEN:
            return 1e6
        d = distances(np.asarray(sig, np.float32), np.asarray([lk[0] for lk in looks], np.float32))[0]
        best = 1e6
        for k, (_, size, look_elong) in enumerate(looks):
            dk = float(d[k])
            if area and size:
                dk += SIZE_WEIGHT * max(0.0, abs(float(np.log(area / size))) - float(np.log(SIZE_FREE)))
            if elong and look_elong:
                dk += ELONG_WEIGHT * abs(elong - look_elong)
            best = min(best, dk)
        return best

    def recognizable(self, sig: np.ndarray, area: float = 0.0, strict: bool = False) -> bool:
        """Looks like a registered character (closely, or much more than like anybody else); `strict`: closely, and
        more than like anybody else."""
        order = self._looks()[0]
        row = self._unlike_all(sig, area)
        ds = sorted(float(row[k]) for k, i in enumerate(order) if len(i.signature))
        if not ds:
            return False
        if strict:
            return ds[0] < ID_ACCEPT and (len(ds) == 1 or ds[1] - ds[0] >= ID_MARGIN)
        return ds[0] < ID_ACCEPT or ds[0] < ID_ACCEPT_LOOSE and (len(ds) == 1 or ds[1] - ds[0] >= ID_MARGIN_LOOSE)

    def _position(self, o: Observation, category: str | None) -> tuple[float, float]:
        key = ("pos", category or o.category_guess)        # asked for every track it might be: once is enough
        if key not in o.extra:
            o.extra[key] = o.position(self.calib, category, self.tops)
        return o.extra[key]

    def _associate(self, things: list[Observation], now: float, births: bool = True) -> None:
        """One assignment for all: the tracks in sight by position and colour, the carried ones by colour."""
        tracks = list(self.tracks.values())
        for t in tracks:
            t.obs = None
        matched: set[int] = set()
        if tracks and things:
            cost = np.full((len(tracks), len(things)), 1e6)
            sds = distances(np.asarray([t.sig for t in tracks], np.float32), np.asarray([o.sig for o in things], np.float32))
            for i, t in enumerate(tracks):
                for j, o in enumerate(things):
                    sd = float(sds[i, j])
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
        if t.on_frames >= (ON_FRAMES if fid is not None else OFF_FRAMES):
            t.on = fid                     # some frames alike: no flicker on the edge of the bed
        if t.jumps and now - t.jumps[0] > CAR_SURE_S:     # kept as long as the longest look back (the car's)
            t.jumps = [j for j in t.jumps if now - j <= CAR_SURE_S]
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
                    if t.identity:
                        self._touched.add(t.identity)      # in a hand: it may be put down anywhere
                    break

    def _learn_poses(self, now: float) -> None:
        """A character the house is sure of (confirmed, or recognized with confidence), still, with no hand around
        and seen whole, that looks unlike every pose it knows: this look is one more pose of it."""
        if self._frozen or self._quiet_s < POSE_STEADY_S:
            return
        for t in self.tracks.values():
            ident = self.identities.get(t.identity or "")
            o = t.obs
            if ident is None or o is None or t.carried or t.uncertain or not (t.locked or t.confidence > 0.6):
                continue
            if t.area and o.area_mm2 > 1.5 * t.area:
                continue                       # against another figurine: not its own look
            if self._unlike_of(t.sig, o.area_mm2, ident, o.elongation) <= NEW_POSE:
                continue
            self.add_pose(ident, t.sig, o.area_mm2, o.elongation)

    def add_pose(self, ident: Identity, sig: np.ndarray, area: float, elong: float, taught: bool = False) -> bool:
        """One more look of this character, if it can be one (see fits_pose; `taught`: chosen in the web app)."""
        if not (self.fits_taught if taught else self.fits_pose)(ident, np.asarray(sig, np.float32)):
            return False
        pose = {"sig": [round(float(v), 5) for v in sig], "size": round(float(area), 1),
                "elong": round(float(elong), 2)}
        if taught:
            pose["taught"] = True
        poses = list(ident.poses) + [pose]
        if len(poses) > MAX_POSES:
            # forget the pose most like another one: the variety is what helps
            def nearest(i):
                return min(distance(np.asarray(poses[i]["sig"], np.float32), np.asarray(poses[k]["sig"], np.float32))
                           for k in range(len(poses)) if k != i)
            poses.pop(min(range(len(poses) - 1), key=nearest))
        ident.poses = poses
        self.posed.add(ident.id)
        self._looks_changed()
        return True

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
            if t.identity and t.obs is not None and not t.carried and not t.uncertain:
                # (a name the house is in doubt about says nothing about where that character is)
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

    def touch_all(self) -> None:
        """Every character may have been moved meanwhile (the house was not looking): none is tied to where it was
        last seen until it is seen again."""
        self._touched |= set(self.places) | {t.identity for t in self.tracks.values() if t.identity}

    def _gone_from(self, t: VTrack) -> bool:
        """Not in sight, and a hand has been over its place since: that character may be anywhere now, and its name
        may go to what is seen elsewhere."""
        return t.obs is None and not t.carried and bool(t.identity) and t.identity in self._touched

    def _elsewhere(self, identity: str, t: VTrack) -> bool:
        """This character was last seen far from this track, and no hand has been over that place since: nothing
        moves by itself, so this cannot be it (it is still there, maybe hidden)."""
        p = self.places.get(identity)
        if p is None or identity in self._touched:
            return False
        return float(np.hypot(t.x - p[0], t.y - p[1])) > PLACE_JUMP_MM

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
        if t.identity:
            # the name was on something that is not there: where it stood says nothing about that character
            self.places.pop(t.identity, None)
            self._touched.discard(t.identity)
        self._suppressed.append((t.x, t.y, now + SUPPRESS_S))
        self._doubt_room(t, now)
        return t.raw or (t.x, t.y)

    def _doubt_room(self, t: VTrack, now: float) -> None:
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
        # the only new thing the hands left: sure enough to learn how it looks now (lying down, on the bed)
        best.identity, best.locked = t.identity, t.locked
        best.confidence = max(t.confidence, 0.7 if len(new) == 1 else 0.5)
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
            self._doubt_room(t, now)
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
            # never told to the house, or followed only for a moment (even if it took a name): it was noise
            young = (t.last_seen - t.since < YOUNG_S or not t.shown and not t.identity) and not t.locked
            if young or unseen > (HIDDEN_KNOWN_S if t.identity else HIDDEN_S):
                del self.tracks[tid]
                self._rooms.pop(tid, None)

    # ------------------------------------------------------------ identities
    def _twins(self, t: VTrack) -> bool:
        """Other registered identities that look the same as this one, and could be as big as what is seen."""
        me = self.identities.get(t.identity or "")
        if not me or len(me.signature) == 0:
            return False
        area = t.obs.area_mm2 if t.obs is not None else 0.0
        return any(o.id != me.id and len(o.signature) and distance(me.signature, o.signature) < ID_ACCEPT
                   and self.fits_size(o, area) for o in self.identities.values())

    @staticmethod
    def fits_size(ident: Identity, area: float) -> bool:
        """Can a blob this big be this character? The car only car-sized, a figurine never car-sized, and nobody
        more than SIZE_ODD times bigger or smaller than every look it has (as registered, and the poses learned)."""
        if not area:
            return True
        if (ident.category == CAR) != (area >= CAR_MIN_MM2) and (ident.category == CAR or area > FIGURINE_MAX_MM2):
            return False
        sizes = [s for s in [ident.size] + [p.get("size", 0.0) for p in ident.poses] if s]
        return not sizes or any(1.0 / SIZE_ODD <= area / s <= SIZE_ODD for s in sizes)

    def _doubt(self, t: VTrack, now: float) -> None:
        t.locked = False
        t.uncertain = True
        me = self.identities.get(t.identity or "")
        alike = [o for o in self.identities.values()
                 if me and len(o.signature) and distance(me.signature, o.signature) < ID_ACCEPT]
        t.candidates = [o.id for o in sorted(alike, key=lambda o: distance(t.sig, o.signature))]   # likeliest first
        self._ask(t, now)

    def _possible(self, t: VTrack, ids: Iterable[str], now: float) -> list[str]:
        """The names this track can have. A name is never in two places: not one already recognized somewhere else
        in the house (unless a hand has been over its place since), not one last seen far from here with no hand
        there since; nobody much bigger or smaller than what is seen (a figurine is never the car); and the car only
        in the garage, or when the house is certain of it."""
        held = {u.identity for u in self.tracks.values()
                if u is not t and u.identity and not u.uncertain and not u.carried
                and (u.obs is not None or u.identity not in self._touched)}
        car_ok = self.layout.locate(t.x, t.y) == "garage" or (
            t.obs is not None and t.obs.area_mm2 > FIGURINE_MAX_MM2 and not self._car_out_of_place(t, now))
        area = t.obs.area_mm2 if t.obs is not None else 0.0
        out = []
        for i in ids:
            ident = self.identities.get(i)
            if ident is None or i in held or (i != t.identity and self._elsewhere(i, t)):
                continue
            if (ident.category == CAR and not car_ok) or not self.fits_size(ident, area):
                continue
            out.append(i)
        return out

    def _settle(self, t: VTrack, now: float) -> bool:
        """Of the names it was in doubt between, only one can still be this track: the house takes it without
        asking (Rossellina is in the kitchen, so the newcomer in the living room is Rosaria). False if the doubt
        stays."""
        left = self._possible(t, t.candidates, now)
        if len(left) > 1:
            t.candidates = left
            if t.identity not in left:
                t.identity = left[0]          # the name it had is somewhere else now: the likeliest of the others
            return False
        if left:
            ident = self.identities[left[0]]
            t.identity, t.category = ident.id, ident.category
            t.confidence = max(t.confidence, 0.5)
        else:
            # none of them can be here (each one is somewhere else, or of another size): somebody else, and the
            # house asks who
            t.identity, t.confidence, t.locked = None, 0.0, False
            t.votes.clear()
        t.uncertain, t.candidates = False, []
        return True

    def _settle_doubts(self, now: float) -> None:
        for t in self.tracks.values():
            if t.uncertain and t.candidates:
                self._settle(t, now)

    def _ask(self, t: VTrack, now: float) -> None:
        if not self.on_question or now - t.asked <= 30 or not t.candidates or self._car_out_of_place(t, now):
            return
        if self._settle(t, now):
            return                        # only one of them can be here: nothing to ask
        t.asked = now
        self.on_question(t, list(t.candidates))

    def _car_out_of_place(self, t: VTrack, now: float) -> bool:
        """A car (or something car-sized) out of the garage that the house is not certain of: no question."""
        car = t.category == CAR or (t.obs is not None and t.obs.area_mm2 > FIGURINE_MAX_MM2)
        if not car or self.layout.locate(t.x, t.y) == "garage":
            return False
        steady = (t.obs is not None and now - t.since >= CAR_SURE_S and self.presence(t, now) >= CAR_SURE_PRESENCE
                  and not any(now - j <= CAR_SURE_S for j in t.jumps))
        return not steady

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

    def together(self, track_id: str, identities: list[str], now: float) -> None:
        """Somebody said these characters are all there, touching each other: one blob for all of them. The one
        that looks most like the blob takes the track; the others stand at the same place, hidden behind it,
        until a hand parts them."""
        t = self.tracks.get(track_id)
        ids = [i for i in dict.fromkeys(identities) if i in self.identities]
        if t is None or not ids:
            return
        ids.sort(key=lambda i: self._unlike_of(t.sig, 0.0, self.identities[i]))
        self.assign(track_id, ids[0])
        for ident in ids[1:]:
            for tid in [k for k, u in self.tracks.items() if u is not t and u.identity == ident]:
                del self.tracks[tid]              # it was not where the house thought: it is here
                self._rooms.pop(tid, None)
            hidden = VTrack(new_id("t"), t.x, t.y, None, np.array(t.sig, np.float32), self.identities[ident].category,
                            identity=ident, locked=True, confidence=1.0, last_seen=now, since=now, born=self.frame,
                            hits=NEW_HITS, shown=True)
            self.tracks[hidden.id] = hidden
            self.places[ident] = (t.x, t.y, now)
            self._touched.discard(ident)

    def forget(self, identity: str) -> None:
        for t in self.tracks.values():
            if t.identity == identity:
                t.identity, t.locked, t.confidence = None, False, 0.0
        self.identities.pop(identity, None)
        self.places.pop(identity, None)
        self._looks_changed()

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
        order = self._looks()[0]
        index = {ident.id: k for k, ident in enumerate(order)}
        rows = {t.id: self._unlike_all(t.sig, t.obs.area_mm2 if t.obs is not None else 0.0,
                                       t.obs.elongation if t.obs is not None else 0.0) for t in free_tracks}
        if not (self._frozen or self._quiet_s <= HAND_RECENT_S):
            # no hand around: names do not move. A figurine with a name keeps it while it still looks like that
            # character (two of the same colour do not swap names because of a shadow)
            free_tracks = [t for t in free_tracks if not (t.identity in index and
                                                          rows[t.id][index[t.identity]] < ID_ACCEPT_LOOSE)]
            if not free_tracks:
                return
        taken = {t.identity for t in self.tracks.values() if t.identity and t not in free_tracks
                 and not self._gone_from(t)}
        cands = [i for i in ids if i.id not in taken]
        raw = np.ones((len(free_tracks), max(len(cands), 1)))     # how much it looks like each one
        for i, t in enumerate(free_tracks):
            for j, ident in enumerate(cands):
                raw[i, j] = rows[t.id][index[ident.id]]
        cost = raw.copy()
        for i, t in enumerate(free_tracks):
            for j, ident in enumerate(cands):
                if any(u.identity == ident.id for u in free_tracks if u is not t):
                    cost[i, j] = 1e6          # held by another track in sight
                elif t.identity != ident.id and self._elsewhere(ident.id, t):
                    cost[i, j] = 1e6          # last seen somewhere else, and no hand has been there since
        best_of = dict(zip(*linear_sum_assignment(cost))) if cands else {}
        for i, t in enumerate(free_tracks):
            j = best_of.get(i)
            d = cost[i, j] if j is not None else 1.0
            if d >= 1e6:
                j, d = None, 1.0
            # names that cannot be this one (recognized elsewhere, last seen elsewhere, the car out of the garage)
            # do not count, not even to make a doubt
            ok = set(self._possible(t, (c.id for c in cands), now))
            if j is not None and cands[j].id not in ok:
                given = {best_of[i2] for i2 in best_of if i2 != i and cost[i2, best_of[i2]] < ID_ACCEPT_LOOSE}
                rest = [k for k in range(len(cands)) if cands[k].id in ok and cost[i, k] < 1e6 and k not in given]
                j = min(rest, key=lambda k: raw[i, k]) if rest else None
                d = raw[i, j] if j is not None else 1.0
            # twins are told by how much it looks like each of them, whoever holds the name
            others = sorted(raw[i, k] for k in range(len(cands)) if k != j and cands[k].id in ok) if j is not None else []
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
            close = [cands[k].id for k in np.argsort(raw[i]) if raw[i, k] < ID_ACCEPT and cands[k].id in ok]
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
            # the same character still "in a hand", or unseen where a hand has been: it was put down here
            for tid in [k for k, c in self.tracks.items()
                        if c is not t and c.identity == ident.id and (c.carried or self._gone_from(c))]:
                del self.tracks[tid]
                self._rooms.pop(tid, None)
            if not ambiguous:
                t.uncertain, t.candidates = False, []

    def adopt(self, o: Observation, now: float, pointed: bool = False) -> VTrack | None:
        """A new track for something that stands out and stays, though no hand was seen putting it down. `pointed`:
        somebody pointed at it in the web app: it is there at once, wherever it is, and the house does not ask who it
        is (that somebody is telling it)."""
        x, y = self._position(o, o.category_guess)
        if pointed:
            self._suppressed = [s for s in self._suppressed if np.hypot(s[0] - x, s[1] - y) > SUPPRESS_MM]
        elif self.suppressed(x, y, now):
            return None
        t = VTrack(new_id("t"), x, y, o, o.sig, o.category_guess, last_seen=now, since=now, born=self.frame)
        self.tracks[t.id] = t
        self._apply(t, o, now)
        o.extra["track"] = t.id
        if pointed:
            t.hits, t.shown, t.asked_new = max(t.hits, NEW_HITS), True, now
            t.presence = 1.0
        return t

    def _ask_unknown(self, now: float) -> None:
        """In sight for a while and recognized as nobody: ask who it is. The registered characters that are
        not in the house are proposed, closest colours first, then those whose colours the house has not
        learned yet (the answer teaches them)."""
        if not self.on_question:
            return
        held = {t.identity for t in self.tracks.values() if t.identity and not self._gone_from(t)}
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
            if kind == CAR and self._car_out_of_place(t, now):
                continue                       # asked later, if it stays and the house becomes certain
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
