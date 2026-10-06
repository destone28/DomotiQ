# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Everything between a frame and the tracks, without the camera.

The worker process feeds it the frames of the webcam; the tests feed it
synthetic ones. It owns the calibration, the empty-house reference, the
tracker, the privacy filter, the captures and the recordings.

Figurines do not move by themselves: every change in the house is made by a
hand. So:
- while a hand is over the house, and for a moment after it leaves (its
  shadow, the figurine still swinging), the house is "frozen": nothing new
  is counted and nothing disappears, and every piece of the arm is the hand;
- after that, new things are looked for only where the hand was;
- a change with no hand around (a reflection, the light of the hall) is not a
  presence: after a few seconds it becomes part of the empty house;
- much of the house changing at once with no hand is the light of the hall:
  the light of every room is measured again, and the house waits.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from ..layout import Layout
from ..model import CATEGORY_NAMES, Identity, Track
from .geometry import Calibration
from .pipeline import Observation, Segmenter
from .privacy import Privacy
from .scene import StaticScene
from .signature import SIG_LEN, distance, signature, to_hex
from .tracker import ID_ACCEPT, Tracker

log = logging.getLogger(__name__)

ANALYSIS = (640, 480)
EMPTY_FRAMES = 20
NOISE_FILE = "noise.npy"     # the noise of every pixel, measured with the empty house, next to its image
SETTLE_S = 0.6           # after the last hand: its shadow is gone and what it put down stands still
BIRTH_S = 3.0            # new things are looked for where the hands were, for this long
SCAN_S = 3.0             # after a start or a new empty house, what is in sight is taken as it is
LIGHT_SHARE = 0.20       # this much of the house changed at once with no hand: the light of the hall changed
LIGHT_FREEZE_S = 4.0     # ...the house waits this long for the light to be measured again
GHOST_FRAMES = 25        # a change explained by nothing for this many frames joins the empty house
LIGHT_BLOCK_S = 2.5      # after the house changes the light of a room, its glow on walls and floor is no presence
LIGHT_GLOW_S = 15.0      # ...and nothing there is taken late: the glow joins the empty house instead. A figurine
                         # put down there is born before: it is what turns the light on
SCAN_CHROMA, SCAN_DARKER = 10.0, 8.0   # at a start, only what clearly stands out: another colour, or darker
SCAN_WAIT_S = 20.0       # a start waits for the lights of the house to settle (they are sent again), at most this long
HAND_STILL_S = 8.0       # a "hand" that does not move for this long is something lying on the edge of the base
LATE_S = 2.0             # something that clearly stands out and stays this long, within LATE_WINDOW_S of a
LATE_WINDOW_S = 20.0     # hand, is a presence even if the house was waiting when it was put down
MIN_FLOOR = 0.35         # share of a new thing seen over floor or furniture: a reflection on a wall has none
EDGE_MM, EDGE_MM2 = 12.0, 600.0   # small things right on the edge of the base are cables and sleeves
FORGET_S, FORGET_MM = 3.0, 30.0   # "there is nothing there": what is seen there now joins the empty house
# What a hand brings: something that was not there before the hand came, compact, and clearly standing out from
# the floor. Measured on casa1, the figurines stand out by 16-53 in colour (or are 15-20 darker) and are at most
# 2.2 times longer than wide; what the light does to the foot of a wall or the edge of the sofa is a thin strip
# (4.5-19 times longer than wide) or a faint patch (9-12 in colour).
BIRTH_ELONGATION = 3.5
BIRTH_CHROMA, BIRTH_DARKER, BIRTH_LIGHTER = 14.0, 12.0, 25.0
# a figurine lying down is longer: up to LYING_ELONGATION when its colour is vivid (the strips of light are faint)
LYING_ELONGATION, VIVID_CHROMA, VIVID_DARKER = 6.5, 20.0, 15.0
BEFORE_HAND_S = 0.5      # different from the empty house since before the hand came: it was already there
HOLE_DIFF = 30.0         # as close as this to the empty house as it was saved (sum over the channels): a hole
# The light of the hall: the webcam is set again on what it sees when the picture stays this much darker or
# brighter than the empty house as it was saved for RETUNE_S, with no hand and no light of the house just changed.
# The empty house and the presences stay as they are: nothing moved, so nothing is born and nothing leaves.
# Measured on casa1: the room light switched off gives 0.45-0.57; the scenes of the house (cinema, night) 0.95.
RETUNE_DARK, RETUNE_BRIGHT = 0.70, 1.43
# "hands" seen without a break for this long are no hands: the walls, lit in another way than in the empty house.
# They do not stop the webcam from being set again, and if the light is close enough they join the empty house
HAND_STUCK_S = 30.0
# the house at rest: a picture like the last one looked at, long after the last hand and with the light still, is not
# looked at again (it costs some 180 ms on the board, the comparison a fraction of a millisecond); one a second always is
REST_AFTER_S = 25.0
REST_MAX_S = 1.0
REST_SIZE = (80, 60)         # the small grey picture compared: each cell is 8 x 8 pixels of the analysed one
REST_DIFF = 6                # grey levels a cell may change by and still be the same picture
RETUNE_S = 5.0
ADOPT_PX = 28            # pointing at something in the web app: the empty house comes back this far around
RETUNE_EVERY_S = 60.0
RETUNE_MAX_S = 900.0     # a retune that did not bring the picture back near the empty house (a hall darker than the
                         # webcam can follow) waits twice as long before the next one, up to this: on casa1 the
                         # webcam was set again every 70 s with the same values, and the presences went every time
NO_HAND_S = 1.0          # a difference that appeared this long after the last hand is light, never a presence
COCO_CLASSES = ["person", "dog", "cat", "animal", "car", "object"]


class Engine:
    def __init__(self, layout: Layout, calib_dir: Path, dataset_dir: Path, recordings_dir: Path,
                 grab: Callable[[int], list[np.ndarray]] | None = None) -> None:
        self.layout = layout
        self.dir = calib_dir
        self.dataset_dir = dataset_dir
        self.recordings_dir = recordings_dir
        self.grab = grab                           # returns n new frames, for the calibration commands
        for d in (calib_dir, dataset_dir, recordings_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.calib: Calibration | None = None
        self.segmenter: Segmenter | None = None
        self.tracker: Tracker | None = None
        self.privacy: Privacy | None = None
        self.identities: list[Identity] = []
        self.frame: np.ndarray | None = None        # the last frame, at analysis size
        self.frame_at = 0.0
        self.observations: list[Observation] = []
        self.tracks: list[Track] = []
        self.fps = 0.0
        self.proc_ms = 0.0
        self.stage_ms = {"segment": 0.0, "tracker": 0.0, "rest": 0.0}   # where the time of a frame goes
        self.on_question: Callable[[Track, list[str]], None] | None = None
        self._record: dict[str, Any] | None = None
        self._last_ref_update = 0.0
        self._moved = {"checked": 0.0, "shift": 0.0, "count": 0}
        self._background: dict[str, np.ndarray] = {}
        self._flooded_since = 0.0
        self.light_ok = True                       # the worker clears it while the webcam light is not set
        self.blur_private = True                   # the bathroom blurred in the images that leave the board
        self._hand_at = float("-inf")              # the last frame with a hand over the house
        self._hands_since = 0.0                    # since when hands have been seen without a break
        self._stuck = False                        # those "hands" have been there too long to be hands
        self._zone: np.ndarray | None = None       # where the hands have been since the last births
        self._scan_pending = True
        self._scan_until = 0.0
        self._scan_since = 0.0
        self._light_since = 0.0
        self._ghost: np.ndarray | None = None      # frames of unexplained change, per pixel
        self.absorbed = 0
        self._light_block: dict[str, float] = {}  # room -> until when a change of its light hides births
        self._light_at: dict[str, float] = {}     # room -> when the house last changed its light
        self._animated: set[str] = set()           # rooms whose light is animated now
        self.paused = False                        # a party: what is seen is not looked at until it ends
        self._thumb: np.ndarray | None = None      # the small grey picture of the last frame
        self._rest_ref: np.ndarray | None = None   # ...and of the last frame looked at
        self._rest_at = 0.0
        self.rest_diff = 0.0                       # how much the pictures at rest differ (for the diagnostics)
        self.rested = 0                            # frames not looked at because nothing had changed
        self.looked = 0
        self._forget: list[tuple[float, float, float]] = []   # (x, y, until): somebody said nothing is there
        self._fg_since: np.ndarray | None = None   # per pixel: since when it differs from the empty house
        self._session_at = float("-inf")          # when the hands now at work came
        self._empty0: np.ndarray | None = None     # the empty house as it was saved, before anything joined it
        self._ratio = 1.0                          # brightness of the picture / of the empty house
        self._off_since = 0.0                      # since when that ratio is beyond RETUNE_DARK..RETUNE_BRIGHT
        self._settle_until = 0.0                   # the webcam has just been set again: the house waits
        self._retuned_at = float("-inf")
        self.retunes = 0
        self._retune_every = RETUNE_EVERY_S
        self._back_since_retune = True     # the picture came near the empty house again after the last retune
        self.holes = 0
        self._clipped_since = 0.0                  # since when the light is beyond what the rooms can correct
        self._hand_since: np.ndarray | None = None # since when each pixel has been part of a hand (0: not)
        # before the calibration the house does not know where the bathroom is: it assumes the
        # camera is mounted as in the model, with a wide margin
        self._nominal_privacy = Privacy(layout, Calibration.synthetic(*ANALYSIS, layout.camera), margin_mm=45.0)
        self.load()

    # ------------------------------------------------------------ calibration and reference
    @property
    def calibrated(self) -> bool:
        return self.calib is not None and self.segmenter is not None

    @property
    def ready(self) -> bool:
        return self.calibrated and self.segmenter.reference is not None and self.light_ok

    def retune_wanted(self, now: float) -> bool:
        """The picture has stayed much darker or brighter than the empty house, with no hand and no light of
        the house just changed: the webcam must be set again."""
        return (self.ready and self.light_ok and bool(self._off_since) and now - self._off_since >= RETUNE_S
                and (now - self._hand_at >= RETUNE_S or self._stuck) and now - self._retuned_at >= self._retune_every
                and not self._animated and all(now - t >= LIGHT_GLOW_S for t in self._light_at.values()))

    def light_retuned(self, now: float) -> None:
        """The webcam has been set again: the light of every room is measured afresh, and the house waits a
        moment. The empty house, the presences and who they are do not change."""
        self.retunes += 1
        self._retuned_at = now
        self._retune_every = RETUNE_EVERY_S if self._back_since_retune else min(2 * self._retune_every, RETUNE_MAX_S)
        self._back_since_retune = False
        self._off_since = self._clipped_since = 0.0
        self._hands_since, self._stuck = 0.0, False
        self._settle_until = now + LIGHT_FREEZE_S
        if self.segmenter:
            self.segmenter.light_changed(self.segmenter.region_names, now, LIGHT_FREEZE_S)
            # other exposure and gain, other noise: learned again from the next quiet frames, after a restart too
            self.segmenter.set_noise(None)
            (self.dir / NOISE_FILE).unlink(missing_ok=True)

    def dismiss(self, track_id: str, now: float | None = None) -> None:
        """Somebody said there is nothing there (a reflection, a hand): the track goes, what it was joins the
        empty house, and nothing is born there for a while."""
        now = time.time() if now is None else now
        where = self.tracker.dismiss(track_id, now) if self.tracker else None
        if where:
            self._forget.append((where[0], where[1], now + FORGET_S))

    def _forget_dismissed(self, small: np.ndarray, obs: list[Observation], now: float) -> list[Observation]:
        self._forget = [f for f in self._forget if f[2] > now]
        seg = self.segmenter
        if not self._forget or seg.labels is None:
            return obs
        keep, where = [], np.zeros(seg.labels.shape, bool)
        for o in obs:
            cx, cy = o.centroid_mm
            if not o.hand and any(np.hypot(cx - x, cy - y) < FORGET_MM for x, y, _ in self._forget):
                x, y, w, h = o.bbox
                where[y:y + h, x:x + w] |= seg.labels[y:y + h, x:x + w] == o.extra["label"]
            else:
                keep.append(o)
        if where.any():
            where = cv2.dilate(where.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            seg.absorb(small, where & (seg.mask > 0))
            self.absorbed += 1
        return keep

    def adopt_at(self, u: float | None = None, v: float | None = None, x_mm: float | None = None,
                 y_mm: float | None = None, now: float | None = None) -> dict[str, Any]:
        """Somebody points at something the house does not follow (in the picture, `u` and `v` from 0 to 1, or on the
        plan, in mm): around that point the empty house comes back as it was saved, so what had joined it there (a
        figurine the house did not recognize) shows again, and what differs from it becomes a presence."""
        now = time.time() if now is None else now
        seg = self.segmenter
        if not self.ready or self.frame is None or self.tracker is None or seg is None:
            return {"ok": False, "error": "not_ready"}
        if x_mm is not None and y_mm is not None:
            px, py = (float(c) for c in self.calib.image_of(np.array([[float(x_mm), float(y_mm)]]), 20.0)[0])
        elif u is not None and v is not None:
            px, py = float(u) * ANALYSIS[0], float(v) * ANALYSIS[1]
        else:
            return {"ok": False, "error": "where"}

        def under(o: Observation, margin: float) -> bool:
            x, y, w, h = o.bbox
            return x - margin <= px <= x + w + margin and y - margin <= py <= y + h + margin
        for t in self.tracker.tracks.values():
            if t.obs is not None and not t.carried and under(t.obs, 6):
                return {"ok": True, "track": t.id, "existing": True}
        if self._empty0 is not None:
            region = np.zeros(seg.reference_bgr.shape[:2], np.uint8)
            cv2.circle(region, (int(round(px)), int(round(py))), ADOPT_PX, 1, -1)
            region = (region > 0) & (seg.mask > 0)
            if region.any():
                seg.reference_bgr[region] = self._empty0[region]
                ys, xs = np.nonzero(region)
                seg._reference_changed((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        # where somebody said "nothing there" a while ago is not forgotten any more
        cx, cy = (float(c) for c in self.calib.to_floor(np.array([[px, py]]))[0]) if x_mm is None else (x_mm, y_mm)
        self._forget = [f for f in self._forget if np.hypot(f[0] - cx, f[1] - cy) >= FORGET_MM]
        obs, _fg, _lab = seg.process(self.frame, now)
        near = [o for o in obs if not o.hand and under(o, 12)]
        if not near:
            return {"ok": False, "error": "nothing"}
        o = min(near, key=lambda o: float(np.hypot(o.center_px[0] - px, o.center_px[1] - py)))
        t = self.tracker.adopt(o, now, pointed=True)
        if t is None:
            return {"ok": False, "error": "nothing"}
        return {"ok": True, "track": t.id, "existing": False}

    def together(self, track_id: str, identities: list[str], now: float | None = None) -> None:
        """Somebody said that what the house sees there is these characters, touching: all of them are there."""
        if self.tracker:
            self.tracker.together(track_id, identities, time.time() if now is None else now)

    def lights_changed(self, rooms: list[str], now: float, animated: list[str] | None = None) -> None:
        """The house changed the light of these rooms: measure it again, and its glow is no presence.
        `animated`: the rooms whose light is animated now (a party, breathing): figurines there may shake."""
        if self.segmenter:
            self.segmenter.light_changed(rooms, now)
        if animated is not None:
            self._animated = set(animated)
        for room in rooms:
            self._light_block[room] = now + LIGHT_BLOCK_S
            self._light_at[room] = now

    def pause(self, on: bool, now: float | None = None) -> None:
        """A party: the coloured lights change every moment, and what the webcam sees then says nothing about what
        is in the house. Until it ends the presences stay as they are, where they are. Then the light of every
        room is measured again, every character may have been moved meanwhile, and what is in sight is taken as it
        is once the lights stand still (as at a start)."""
        now = time.time() if now is None else now
        if bool(on) == self.paused:
            return
        self.paused = bool(on)
        if self.paused:
            return
        self._settle_until = now + LIGHT_FREEZE_S
        if self.segmenter:
            self.segmenter.light_changed(self.segmenter.region_names, now, LIGHT_FREEZE_S)
        if self.tracker:
            self.tracker.touch_all()
        self._scan_pending, self._scan_since = True, 0.0
        self._zone, self._ghost = None, None

    def _resting(self, small: np.ndarray, now: float) -> bool:
        """The house at rest and this picture like the last one looked at: no hand for REST_AFTER_S, no light of the
        house changing or animated, nothing pending (a scan, a recording), and no cell of the small grey picture
        changed by more than REST_DIFF. A hand changes it at once; at least one frame a second is looked at."""
        thumb = cv2.resize(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), REST_SIZE, interpolation=cv2.INTER_AREA)
        self._thumb = thumb.astype(np.int16)
        ref = self._rest_ref
        if ref is None or ref.shape != self._thumb.shape:
            return False
        diff = float(np.abs(self._thumb - ref).max())
        self.rest_diff = 0.9 * self.rest_diff + 0.1 * diff
        if self._record or self._scan_pending or now < self._scan_until or now < self._settle_until:
            return False
        if now - self._hand_at < REST_AFTER_S or now - self._rest_at >= REST_MAX_S or self._animated:
            return False
        if self._light_since or self._clipped_since or self._off_since or self._flooded_since:
            return False
        if any(now - t < LIGHT_GLOW_S for t in self._light_at.values()):
            return False
        return diff <= REST_DIFF

    def _plausible(self, o: Observation, now: float) -> bool:
        """Could this be something standing in the house (whatever put it there)?"""
        if o.extra.get("floor", 1.0) < MIN_FLOOR:
            return False                      # all on a wall: a reflection
        if o.area_mm2 < 6000 and not self._known(o):
            if o.elongation > self._longest(o):
                return False                  # a thin strip: the foot of a wall, the edge of the furniture
            chroma_d, light_d = o.extra.get("contrast", (0.0, 0.0))
            if chroma_d < BIRTH_CHROMA and -BIRTH_DARKER < light_d < BIRTH_LIGHTER:
                return False                  # a faint patch: the light, not a figurine
        b = self.layout.base
        cx, cy = o.centroid_mm
        if min(cx - b.x0, b.x1 - cx, cy - b.y0, b.y1 - cy) < EDGE_MM and o.area_mm2 < EDGE_MM2:
            return False
        room = self.layout.locate(cx, cy)
        return self._light_block.get(room or "", 0.0) <= now

    def _known(self, o: Observation) -> bool:
        """Looks like a registered character."""
        return bool(self.tracker) and self.tracker.recognizable(o.sig, o.area_mm2)

    @staticmethod
    def _longest(o: Observation) -> float:
        """How much longer than wide a figurine can be: more when lying down, which only a vivid one may."""
        chroma_d, light_d = o.extra.get("contrast", (0.0, 0.0))
        return LYING_ELONGATION if chroma_d >= VIVID_CHROMA or light_d <= -VIVID_DARKER else BIRTH_ELONGATION

    def _figurine_like(self, o: Observation) -> bool:
        """Compact and clearly standing out from the floor, as a figurine is (whether a hand brought it or not)."""
        if o.hand or not 150 <= o.area_mm2 <= 6000 or o.elongation > self._longest(o):
            return False
        if o.extra.get("floor", 1.0) < MIN_FLOOR:
            return False
        chroma_d, light_d = o.extra.get("contrast", (0.0, 0.0))
        return chroma_d >= BIRTH_CHROMA or light_d <= -BIRTH_DARKER or light_d >= BIRTH_LIGHTER

    def _light_ratio(self, small: np.ndarray) -> float:
        """How bright the picture is against the empty house as it was saved (the light the webcam was set for)."""
        seg = self.segmenter
        ref = self._empty0 if self._empty0 is not None else seg.reference_bgr
        level = cv2.mean(small, mask=seg.mask)[:3]
        ref_level = cv2.mean(ref, mask=seg.mask)[:3]
        return (sum(level) + 3.0) / (sum(ref_level) + 3.0)

    def _absorb_stuck(self, small: np.ndarray, hands: np.ndarray) -> None:
        seg = self.segmenter
        keep = np.zeros(hands.shape, bool)
        for t in self.tracker.tracks.values() if self.tracker else ():
            if t.obs is not None:
                x, y, w, h = t.obs.bbox
                keep[max(0, y - 8):y + h + 8, max(0, x - 8):x + w + 8] = True
        where = hands & (seg.mask > 0) & ~keep
        if where.any():
            seg.absorb(small, where)
            self.absorbed += 1
        if self._hand_since is not None:
            self._hand_since[:] = 0.0

    def _fill_hole(self, o: Observation) -> bool:
        """What is seen there is the empty house as it was saved: something that had joined the empty house (a
        figurine the house did not recognize) has been taken away, and left its place behind. The empty house
        gets its place back; it is no presence."""
        seg = self.segmenter
        if self._empty0 is None or seg.labels is None or self.frame is None:
            return False
        x, y, w, h = o.bbox
        blob = seg.labels[y:y + h, x:x + w] == o.extra["label"]
        if not blob.any():
            return False
        # the frame brought back to the light of the empty house, only where the blob is (the whole frame for
        # every blob of every frame would take most of the time of a frame)
        crop = self.frame[y:y + h, x:x + w].astype(np.float32)
        gains = seg._g[y:y + h, x:x + w] if seg._g is not None else 1.0
        cur = np.minimum(crop / gains, 255.0)[blob]
        empty = self._empty0[y:y + h, x:x + w][blob]
        now_ref = seg.reference_bgr[y:y + h, x:x + w][blob]
        d_empty = float(np.median(np.abs(cur - empty).sum(axis=1)))
        d_ref = float(np.median(np.abs(cur - now_ref).sum(axis=1)))
        if d_empty >= HOLE_DIFF or d_empty >= 0.5 * d_ref:
            return False
        region = np.zeros(seg.labels.shape, bool)
        region[y:y + h, x:x + w] = blob
        region = cv2.dilate(region.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        seg.reference_bgr[region] = self._empty0[region]
        ys, xs = np.nonzero(region)
        seg._reference_changed((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        self.holes += 1
        return True

    def _appeared(self, o: Observation) -> float:
        """Since when what it covers differs from the empty house (0 if unknown)."""
        if self._fg_since is None or self.segmenter.labels is None:
            return 0.0
        x, y, w, h = o.bbox
        blob = self.segmenter.labels[y:y + h, x:x + w] == o.extra["label"]
        return float(np.median(self._fg_since[y:y + h, x:x + w][blob])) if blob.any() else 0.0

    def _may_be_born(self, o: Observation, scan: bool, births_open: bool, now: float) -> bool:
        x, y, w, h = o.bbox
        if births_open and not scan and o.extra.get("floor", 1.0) >= MIN_FLOOR \
                and self._zone[y:y + h, x:x + w].any():
            o.extra["place"] = True           # where the hands were: a figurine they held may be here, as it lies
        if not self._plausible(o, now):
            return False
        if scan:
            # at a start the empty house may be old (other lights on, modules moved meanwhile): the house takes
            # the characters it knows closely, shaped like figurines, and the car; anything else joins the empty
            # house, and a figurine that was already there shows up as soon as somebody moves it
            chroma_d, light_d = o.extra.get("contrast", (0.0, 0.0))
            if chroma_d < SCAN_CHROMA and light_d > -SCAN_DARKER:
                return False
            if o.area_mm2 > 6000:
                return True
            return self._figurine_like(o) and bool(self.tracker) and self.tracker.recognizable(o.sig, o.area_mm2, strict=True)
        if not births_open or not self._zone[y:y + h, x:x + w].any():
            return False
        # brought by the hand: it was not there before the hand came, and it is not the place a hand has just
        # emptied
        appeared = self._appeared(o)
        if appeared and appeared < self._session_at - BEFORE_HAND_S:
            return False
        return not self._fill_hole(o)

    def rescan(self) -> None:
        """Take what is in sight as it is (after a start, or a new empty house)."""
        self._scan_pending = True
        self._zone, self._ghost = None, None
        self._hand_at = float("-inf")

    def load(self) -> None:
        calib = Calibration.load(self.dir / "calibration.json")
        if calib and calib.valid:
            self._setup(calib.scaled(*ANALYSIS) if (calib.width, calib.height) != ANALYSIS else calib)
            ref = cv2.imread(str(self.dir / "reference.png"))
            if ref is not None and ref.shape[1::-1] == ANALYSIS:
                self.segmenter.set_reference([ref])
                self.segmenter.set_noise(self._load_noise())
                self._empty0 = self.segmenter.reference_bgr.copy()
                self._backgrounds()

    def _load_noise(self) -> np.ndarray | None:
        """The noise saved with the empty house (None: the first quiet frames after the start will teach it)."""
        try:
            noise = np.load(self.dir / NOISE_FILE, allow_pickle=False)
        except (OSError, ValueError, EOFError):         # missing, or cut short by a power cut
            return None
        return noise.astype(np.float32) if noise.shape == (ANALYSIS[1], ANALYSIS[0], 2) else None

    def _setup(self, calib: Calibration) -> None:
        self.calib = calib
        self.segmenter = Segmenter(self.layout, calib)
        tracker = Tracker(self.layout, calib)
        tracker.set_identities(self.identities)
        tracker.on_question = self._question
        self.tracker = tracker
        self.privacy = Privacy(self.layout, calib, private=self.blur_private, outside=True)

    def set_privacy(self, blur_private: bool) -> None:
        self.blur_private = bool(blur_private)
        if self.calib is not None:
            self.privacy = Privacy(self.layout, self.calib, private=self.blur_private, outside=True)

    def _question(self, vt, candidates: list[str]) -> None:
        if self.on_question is not None:
            self.on_question(vt.to_track(self.layout, self.tracker._rooms.get(vt.id)), candidates)

    def set_identities(self, identities: list[Identity]) -> None:
        self.identities = identities
        if self.tracker:
            self.tracker.set_identities(identities)

    def _backgrounds(self) -> None:
        """Colours of the floor, walls and lawns: a figurine too close to them is hard to see."""
        seg = self.segmenter
        lab = seg.reference
        scene = seg.scene
        self._background = {}
        free_floor = (scene.z < 0.5) & (seg.mask > 0)
        lawn = np.zeros(free_floor.shape, np.uint8)
        for r in self.layout.raw.get("lawns", []):
            cv2.fillPoly(lawn, [np.round(self.calib.rect_polygon(r)).astype(np.int32)], 255)
        groups = {
            "floor": free_floor & (lawn == 0),
            "lawn": free_floor & (lawn > 0),
            "wall": scene.kind == StaticScene.KINDS["wall"],
        }
        for name, m in groups.items():
            px = lab[m]
            if len(px) > 50:
                self._background[name] = signature(px[:: max(1, len(px) // 5000)])

    def set_corners(self, points: list[list[float]]) -> dict[str, Any]:
        if len(points) != 4:
            return {"ok": False, "error": "four corners are needed"}
        calib = Calibration.from_corners(points, ANALYSIS[0], ANALYSIS[1], self.layout.camera)
        # a sanity check: the base must come out as a convex shape of sensible size
        quad = np.array(calib.corners, np.float32)
        if not cv2.isContourConvex(quad) or cv2.contourArea(quad) < 0.15 * ANALYSIS[0] * ANALYSIS[1]:
            return {"ok": False, "error": "the corners do not look like the base: tap them in order"}
        calib.save(self.dir / "calibration.json")
        self._setup(calib)
        for name in ("reference.png", NOISE_FILE):
            (self.dir / name).unlink(missing_ok=True)
        return {"ok": True, "message": "Angoli salvati. Ora togli tutto e premi Casa vuota.",
                "message_en": "Corners saved. Now clear the house and press Empty house."}

    def take_empty(self, frames: list[np.ndarray] | None = None) -> dict[str, Any]:
        if not self.calibrated:
            return {"ok": False, "error": "calibrate the corners first"}
        if frames is None:
            if self.grab is None:
                return {"ok": False, "error": "no camera"}
            frames = self.grab(EMPTY_FRAMES)
        frames = [self._fit(f) for f in frames if f is not None]
        if len(frames) < 3:
            return {"ok": False, "error": "no frames from the camera"}
        self.segmenter.set_reference(frames)
        self._empty0 = self.segmenter.reference_bgr.copy()
        cv2.imwrite(str(self.dir / "reference.png"), np.clip(self.segmenter.reference_bgr, 0, 255).astype(np.uint8))
        if self.segmenter.noise is not None:
            # written aside and then renamed: a power cut leaves the old file or the new one, never half of it
            tmp = self.dir / ("tmp-" + NOISE_FILE)
            np.save(tmp, self.segmenter.noise.astype(np.float16))
            tmp.replace(self.dir / NOISE_FILE)
        else:
            (self.dir / NOISE_FILE).unlink(missing_ok=True)
        self._backgrounds()
        self._moved.update(shift=0.0, count=0)
        if self.tracker:
            self.tracker.tracks.clear()             # the house is empty now
        self.rescan()
        return {"ok": True, "message": "Casa vuota salvata.", "message_en": "Empty house saved."}

    def reset(self) -> dict[str, Any]:
        for name in ("calibration.json", "reference.png", NOISE_FILE):
            (self.dir / name).unlink(missing_ok=True)
        self.calib = self.segmenter = self.tracker = self.privacy = None
        self.tracks = []
        return {"ok": True}

    # ------------------------------------------------------------ frames
    @staticmethod
    def _fit(frame: np.ndarray) -> np.ndarray:
        if frame.shape[1::-1] != ANALYSIS:
            return cv2.resize(frame, ANALYSIS, interpolation=cv2.INTER_AREA)
        return frame

    def feed(self, frame: np.ndarray, now: float | None = None) -> list[Track]:
        now = time.time() if now is None else now
        t0 = time.perf_counter()
        small = self._fit(frame)
        if self.frame_at:
            dt = max(now - self.frame_at, 1e-3)
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt) if self.fps else 1.0 / dt
        self.frame, self.frame_at = small, now
        if not self.ready:
            self.tracks, self.observations = [], []
            return []
        if self.paused:
            return self.tracks                # the party: the presences as they were, the picture for the live view
        if self._resting(small, now):
            self.rested += 1
            return self.tracks                # nothing has changed since the last frame looked at
        self.looked += 1
        self._rest_ref, self._rest_at = self._thumb, now
        if self._scan_pending:
            # what is in sight is taken as it is only once the lights stand still: the microcontroller sends them
            # again at a start, and their glow is no character
            self._scan_since = self._scan_since or now
            settled = all(now - t >= LIGHT_BLOCK_S for t in self._light_at.values())
            if settled or now - self._scan_since >= SCAN_WAIT_S:
                self._scan_pending, self._scan_until, self._scan_since = False, now + SCAN_S, 0.0
            else:
                self.tracks = self.tracker.update([], now, frozen=True, quiet_s=float("inf"), animated=self._animated)
                return self.tracks
        seg = self.segmenter
        obs, fg, _lab = seg.process(small, now)
        t_seg = time.perf_counter()
        obs = self._forget_dismissed(small, obs, now)
        self._still_hands(small, obs, now)
        hands = seg.hand_mask if seg.hand_mask is not None else np.zeros(fg.shape, bool)
        active = bool(hands.any())
        self._hands_since = (self._hands_since or now) if active else 0.0
        self._stuck = active and now - self._hands_since >= HAND_STUCK_S
        if self._stuck and RETUNE_DARK <= self._light_ratio(small) <= RETUNE_BRIGHT:
            # "hands" that never leave, in a light the webcam need not be set again for: the walls lit another way
            # than in the empty house. They join it as they look now (what stands there is kept)
            self._absorb_stuck(small, hands)
            hands = seg.hand_mask = np.zeros(fg.shape, bool)
            active, self._stuck, self._hands_since = False, False, 0.0
        if active:
            self._hand_at = now
            if self._zone is None:
                self._session_at = now        # a hand comes: what differs from now on may be what it brings
            self._zone = hands.copy() if self._zone is None else (self._zone | hands)
        quiet = now - self._hand_at
        # much of the house changed at once, with no hand: the light of the hall
        changed = float(np.count_nonzero((fg > 0) & ~hands))
        share = changed / max(float(np.count_nonzero(seg.mask)), 1.0)
        if share > LIGHT_SHARE and not active:
            if not self._light_since:
                self._light_since = now
                seg.light_changed(seg.region_names, now, LIGHT_FREEZE_S)
        else:
            self._light_since = 0.0
        light_event = bool(self._light_since) and now - self._light_since < LIGHT_FREEZE_S
        # a light beyond what the correction of the rooms can follow (gains at their limits in most rooms):
        # wait, and then learn the empty house again from what is seen, around the tracks
        g = seg._prev_gains
        clipped = g is not None and float(np.mean(np.any((g <= 0.31) | (g >= 2.95), axis=1))) >= 0.5
        if clipped:
            self._clipped_since = self._clipped_since or now
        else:
            self._clipped_since = 0.0
        relearn = clipped and now - self._clipped_since >= LIGHT_FREEZE_S
        light_event = light_event or clipped or now < self._settle_until
        # most of the house different from the empty one for long: the camera was covered or knocked,
        # or the light changed beyond what the house can follow (a covered camera is just dark: the light
        # correction of the rooms ends at its limit)
        ratio = self._light_ratio(small)
        if share > 0.35 or not 0.33 < ratio < 3.0:
            self._flooded_since = self._flooded_since or now
        else:
            self._flooded_since = 0.0
        self._ratio = ratio
        if RETUNE_DARK <= ratio <= RETUNE_BRIGHT and not clipped and now > self._settle_until:
            self._back_since_retune = True
        if (ratio < RETUNE_DARK or ratio > RETUNE_BRIGHT or clipped) and (not active or self._stuck):
            self._off_since = self._off_since or now
        else:
            self._off_since = 0.0
        # since when each pixel differs from the empty house: what appeared with no hand around is light
        since = self._fg_since
        if since is None or since.shape != fg.shape:
            since = self._fg_since = np.zeros(fg.shape, np.float64)
        diff = fg > 0
        since[diff & (since == 0)] = now
        since[~diff] = 0
        scan = now < self._scan_until
        frozen = (active or quiet < SETTLE_S or light_event) and not scan
        # new things only where the hands were, once they have left
        births_open = self._zone is not None and SETTLE_S <= quiet <= SETTLE_S + BIRTH_S and not light_event
        for o in obs:
            if not o.hand:
                o.extra["birth"] = self._may_be_born(o, scan, births_open, now)
        if self._zone is not None and quiet > SETTLE_S + BIRTH_S:
            self._zone = None
        self.observations = obs
        t_rules = time.perf_counter()
        self.tracks = self.tracker.update(obs, now, frozen=frozen, quiet_s=quiet, animated=self._animated,
                                          hand_mask=hands if active else None)
        t_track = time.perf_counter()
        if relearn:
            self._relearn(small, fg, obs)
        else:
            # figurines put down while the house waited are looked for, but not while the whole picture is
            # changing (a covered camera, the hall light)
            steady = not light_event and share <= 0.35 and 0.33 < ratio < 3.0
            self._absorb_ghosts(small, fg, obs, hands, frozen or scan or share > 0.35, now, steady)
        # the hall light drifts slowly: follow it on the free floor, when nothing moves
        calm = not frozen and not any(o.hand for o in obs)
        drift = calm and now - self._last_ref_update > 5.0
        if drift:
            self._last_ref_update = now
            seg.update_reference(small, fg, rate=0.02)
        # the noise of every pixel too: from every calm frame while it is young (a start with no noise saved, the
        # webcam set again), then with the empty house. Never while a light of the house changes or is animated
        if (drift or seg.noise_young) and calm and not light_event and not self._animated \
                and all(now - t >= LIGHT_BLOCK_S for t in self._light_at.values()):
            seg.learn_noise(self._presences(obs))
        if now - self._moved["checked"] > 30.0:
            self._check_moved(small, now)
        if self._record:
            self._record_frame(small, now)
        t_end = time.perf_counter()
        self.proc_ms = 0.9 * self.proc_ms + 0.1 * (t_end - t0) * 1000.0
        for key, spent in (("segment", t_seg - t0), ("tracker", t_track - t_rules),
                           ("rest", (t_rules - t_seg) + (t_end - t_track))):
            self.stage_ms[key] = 0.9 * self.stage_ms[key] + 0.1 * spent * 1000.0
        return self.tracks

    def _presences(self, obs: list[Observation]) -> np.ndarray | None:
        """Where the blobs that are presences are."""
        labels = self.segmenter.labels
        tracked = [o.extra["label"] for o in obs if o.extra.get("track")]
        if not tracked or labels is None:
            return None
        lut = np.zeros(int(labels.max()) + 1, bool)
        lut[tracked] = True
        return lut[labels]

    def _still_hands(self, small: np.ndarray, obs: list[Observation], now: float) -> None:
        """A hand moves: a "hand" that stays exactly where it is for HAND_STILL_S is a module or a cable lying
        on the edge of the base. It is no hand, and it becomes part of the empty house."""
        seg = self.segmenter
        labels = seg.labels
        hand_labels = [o.extra["label"] for o in obs if o.hand]
        if labels is None:
            return
        if self._hand_since is None or self._hand_since.shape != labels.shape:
            self._hand_since = np.zeros(labels.shape, np.float64)
        since = self._hand_since
        if not hand_labels:
            since[:] = 0.0
            return
        lut = np.zeros(int(labels.max()) + 1, bool)
        lut[hand_labels] = True
        raw = lut[labels]
        since[raw & (since == 0.0)] = now
        since[~raw] = 0.0
        still = []
        for o in obs:
            if not o.hand:
                continue
            x, y, w, h = o.bbox
            blob = labels[y:y + h, x:x + w] == o.extra["label"]
            t0 = since[y:y + h, x:x + w][blob]
            if len(t0) and float(np.mean((t0 > 0) & (now - t0 >= HAND_STILL_S))) > 0.9:
                still.append(o)
        if not still:
            return
        absorb = np.zeros(labels.shape, bool)
        for o in still:
            o.hand = False
            absorb |= labels == o.extra["label"]
        seg.absorb(small, cv2.dilate(absorb.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)
        since[absorb] = 0.0
        self.absorbed += 1
        left = [o.extra["label"] for o in obs if o.hand]
        seg.hand_mask = (cv2.dilate(np.isin(labels, left).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0) \
            if left else np.zeros(labels.shape, bool)
        for o in still:
            obs.remove(o)                     # part of the empty house now
        if self._zone is not None:
            self._zone &= ~absorb

    def _absorb_ghosts(self, small: np.ndarray, fg: np.ndarray, obs: list[Observation], hands: np.ndarray,
                       frozen: bool, now: float = 0.0, steady: bool = True) -> None:
        """What differs from the empty house with no track, no hand and no recent hand to explain it,
        for GHOST_FRAMES frames in a row, becomes part of the empty house. Unless it clearly stands out and
        a hand was around not long ago: then it is a figurine put down while the house was waiting, and it
        gets a track (LATE_S)."""
        seg = self.segmenter
        if self._ghost is None or self._ghost.shape != fg.shape:
            self._ghost = np.zeros(fg.shape, np.uint16)
        explained = hands.copy()
        tracked = [o.extra["label"] for o in obs if o.extra.get("track")]
        if tracked and seg.labels is not None:
            lut = np.zeros(int(seg.labels.max()) + 1, bool)
            lut[tracked] = True
            # a piece of a figurine cut off from its blob still belongs to it
            explained |= cv2.dilate(lut[seg.labels].astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        # what looks like a figurine never joins the empty house: if it is one the house did not recognize, its
        # place would look like a new presence once it is taken away
        keep = [o.extra["label"] for o in obs if not o.extra.get("track") and self._figurine_like(o)
                and not (self._zone is None and self._fill_hole(o))]
        if keep and seg.labels is not None:
            lut = np.zeros(int(seg.labels.max()) + 1, bool)
            lut[keep] = True
            explained |= lut[seg.labels]
        if self._zone is not None:
            explained |= self._zone
        unexplained = (fg > 0) & ~explained
        g = self._ghost
        np.add(g, 1, out=g, where=unexplained & (g < 60000))
        g[~unexplained] = 0
        if steady and now - self._hand_at < LATE_WINDOW_S and seg.labels is not None and self._fg_since is not None:
            for o in obs:
                if o.hand or o.extra.get("track") or not 150 <= o.area_mm2 <= 20000:
                    continue
                chroma_d, light_d = o.extra.get("contrast", (0.0, 0.0))
                if (chroma_d < SCAN_CHROMA and light_d > -SCAN_DARKER) or not self._plausible(o, now):
                    continue
                if now - self._light_at.get(self.layout.locate(*o.centroid_mm) or "", float("-inf")) < LIGHT_GLOW_S:
                    continue                  # the glow of a light the house has just changed
                x, y, w, h = o.bbox
                blob = seg.labels[y:y + h, x:x + w] == o.extra["label"]
                appeared = self._appeared(o)
                if not appeared or now - appeared < LATE_S:
                    continue                  # not standing there long enough yet
                if appeared - self._hand_at > SETTLE_S + NO_HAND_S:
                    continue                  # it appeared with no hand around: a lamp, a shadow
                if appeared < self._session_at - BEFORE_HAND_S:
                    continue                  # it was there before the hand came
                if self._fill_hole(o):
                    continue                  # the place of something a hand took away
                self.tracker.adopt(o, now)
                g[y:y + h, x:x + w][blob] = 0
        if frozen:
            return
        ripe = g >= GHOST_FRAMES
        if ripe.any():
            ripe = (cv2.dilate(ripe.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & (seg.mask > 0) & ~explained
            seg.absorb(small, ripe)
            g[ripe] = 0
            self.absorbed += 1

    def _relearn(self, small: np.ndarray, fg: np.ndarray, obs: list[Observation]) -> None:
        """The empty house again, from this frame, except where the tracks are."""
        seg = self.segmenter
        keep = np.zeros(fg.shape, bool)
        tracked = [o.extra["label"] for o in obs if o.extra.get("track")]
        if tracked and seg.labels is not None:
            lut = np.zeros(int(seg.labels.max()) + 1, bool)
            lut[tracked] = True
            keep = cv2.dilate(lut[seg.labels].astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        seg.absorb(small, (seg.mask > 0) & ~keep)
        seg.light_changed(seg.region_names, self.frame_at, 1.0)
        self._clipped_since = 0.0
        self._zone = None
        self.absorbed += 1

    def _check_moved(self, small: np.ndarray, now: float) -> None:
        """A bumped camera no longer sees the walls where the reference has them."""
        self._moved["checked"] = now
        ref = cv2.cvtColor(np.clip(self.segmenter.reference_bgr, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        cur = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        ref_e = cv2.Canny(ref, 40, 120).astype(np.float32)
        cur_e = cv2.Canny(cur, 40, 120).astype(np.float32)
        win = cv2.createHanningWindow(ref_e.shape[::-1], cv2.CV_32F)
        (dx, dy), response = cv2.phaseCorrelate(ref_e, cur_e, win)
        shift = float(np.hypot(dx, dy))
        self._moved["shift"] = round(shift, 1)
        self._moved["count"] = self._moved["count"] + 1 if shift > 3.0 and response > 0.05 else 0

    @property
    def moved(self) -> bool:
        return self._moved["count"] >= 2

    # ------------------------------------------------------------ queries
    def track_signature(self, track_id: str) -> tuple[list[float], str] | None:
        vt = self.tracker.track(track_id) if self.tracker else None
        if vt is None or len(vt.sig) != SIG_LEN:
            return None
        return [round(float(v), 5) for v in vt.sig], to_hex(vt.sig)

    def category_guess(self, track_id: str) -> str | None:
        vt = self.tracker.track(track_id) if self.tracker else None
        if vt is None or vt.obs is None:
            return None
        return vt.obs.category_guess

    def quality(self, track_id: str) -> list[dict[str, str]]:
        """What could make this one hard to recognize (shown when it is registered)."""
        vt = self.tracker.track(track_id) if self.tracker else None
        if vt is None:
            return []
        out = []
        names = {"floor": ("al pavimento", "the floor"), "lawn": ("ai prati", "the lawns"),
                 "wall": ("alle pareti", "the walls")}
        for key, sig in self._background.items():
            if distance(vt.sig, sig) < 0.22:
                it, en = names[key]
                out.append({"it": f"Il colore è molto simile {it}: potrei non vederlo bene.",
                            "en": f"Its colour is very close to {en}: I may not see it well."})
        age = max(time.time() - vt.since, 1e-3)
        if vt.hits < 0.5 * age * max(self.fps, 1.0) and age > 3:
            out.append({"it": "Compare e scompare: prova a spostarlo in un punto più libero.",
                        "en": "It keeps disappearing: try moving it to a clearer spot."})
        for ident in self.identities:
            if len(ident.signature) == SIG_LEN and distance(vt.sig, ident.signature) < ID_ACCEPT * 0.8:
                out.append({"it": f"Sembra uguale a {ident.name}: li distinguerò solo seguendoli.",
                            "en": f"It looks just like {ident.name}: I will tell them apart only by following them."})
                break
        return out

    def _learnable(self, vt) -> bool:
        """Seen with confidence and looking closely like its character as registered: what it looks like now may
        teach the house (a blob that took the name by mistake must not)."""
        ident = self.tracker.identities.get(vt.identity or "") if self.tracker else None
        return bool(ident is not None and not vt.uncertain and vt.confidence > 0.6 and vt.obs is not None
                    and not vt.carried and self.tracker.fits_pose(ident, vt.sig, ID_ACCEPT))

    def learned(self) -> dict[str, list[float]]:
        """Signatures of the identities seen with confidence, to update their gallery slowly."""
        out = {}
        if not self.tracker:
            return out
        for vt in self.tracker.tracks.values():
            if self._learnable(vt):
                out[vt.identity] = [round(float(v), 5) for v in vt.sig]
        return out

    def learned_poses(self) -> dict[str, list[dict]]:
        """The poses learned since the last call, for the house to keep."""
        if not self.tracker or not self.tracker.posed:
            return {}
        out = {i: list(self.tracker.identities[i].poses) for i in self.tracker.posed if i in self.tracker.identities}
        self.tracker.posed.clear()
        return out

    def learned_sizes(self, identity: str | None = None) -> dict[str, float]:
        """How big the identities seen with confidence look from above (measured with no hand around)."""
        out = {}
        for vt in (self.tracker.tracks.values() if self.tracker else []):
            if vt.identity and vt.area and not vt.carried and (identity is None and self._learnable(vt)
                                                               or vt.identity == identity):
                out[vt.identity] = round(float(vt.area), 1)
        return out

    def status(self) -> dict[str, Any]:
        return {
            "calibrated": self.calibrated,
            "reference": bool(self.ready),
            "fps": round(self.fps, 1),
            "proc_ms": round(self.proc_ms, 1),
            "stage_ms": {k: round(v, 1) for k, v in self.stage_ms.items()},
            "observations": len(self.observations),
            "tracks": len(self.tracks),
            "hands": len(self.tracker.hands) if self.tracker else 0,
            "moved": self.moved,
            "flooded": bool(self._flooded_since and self.frame_at - self._flooded_since > 5.0),
            "light_ok": self.light_ok,
            "hand": bool(self.frame_at - self._hand_at < SETTLE_S),
            "absorbed": self.absorbed,
            "jittery": self.tracker.jittery if self.tracker else 0,
            "brightness": round(self._ratio, 2),
            "holes": self.holes,
            "retunes": self.retunes,
            "shift_px": self._moved["shift"],
            "gains": self.segmenter.gains if self.segmenter else {},
            "recording": bool(self._record),
            "paused": self.paused,
            "rest_diff": round(self.rest_diff, 1),
            "rested": round(self.rested / max(1, self.rested + self.looked), 2),
            "dataset": len(list(self.dataset_dir.glob("*.jpg"))),
        }

    # ------------------------------------------------------------ images that leave the board
    def image(self, overlay: bool = False, calibration: bool = False, width: int = 640) -> np.ndarray | None:
        if self.frame is None:
            return None
        img = (self.privacy or self._nominal_privacy).apply(self.frame)
        if calibration and self.calib:
            self._draw_layout(img)
        if overlay and self.calib:
            self._draw_tracks(img)
        if img.shape[1] != width:
            img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
        return img

    def jpeg(self, overlay: bool = False, calibration: bool = False, quality: int = 72) -> bytes | None:
        img = self.image(overlay, calibration)
        if img is None:
            return None
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def _draw_layout(self, img: np.ndarray) -> None:
        cal = self.calib
        lay = self.layout
        b = lay.base
        cv2.polylines(img, [np.round(cal.rect_polygon([b.x0, b.x1, b.y0, b.y1])).astype(np.int32)], True,
                      (0, 200, 255), 2, cv2.LINE_AA)
        for room in lay.rooms.values():
            r = room.rect
            color = (200, 120, 255) if room.private else (255, 255, 255)
            cv2.polylines(img, [np.round(cal.rect_polygon([r.x0, r.x1, r.y0, r.y1])).astype(np.int32)], True,
                          color, 1, cv2.LINE_AA)
        for d in lay.doors:
            r = d.rect
            cv2.polylines(img, [np.round(cal.rect_polygon([r.x0, r.x1, r.y0, r.y1])).astype(np.int32)], True,
                          (80, 220, 80), 1, cv2.LINE_AA)
        if self.segmenter is not None:
            excl = self.segmenter.mask == 0
            img[excl] = (img[excl] * 0.55).astype(np.uint8)
        # the walls at their real height: they must sit on the walls of the image
        for w in lay.raw.get("walls", []):
            poly = cal.rect_polygon(w["rect"], float(w.get("height", 0)))
            cv2.polylines(img, [np.round(poly).astype(np.int32)], True, (0, 255, 255), 1, cv2.LINE_AA)

    def _draw_tracks(self, img: np.ndarray) -> None:
        cal = self.calib
        names = {i.id: i.name for i in self.identities}
        for t in self.tracks:
            if t.carried:
                continue
            h = 95.0 if t.category == "person" else 45.0
            x, y = cal.image_of(np.array([[t.x, t.y]]), h)[0]
            label = names.get(t.identity or "") or CATEGORY_NAMES.get(t.category, {}).get("it", t.category)
            if t.uncertain:
                label += " ?"
            room = self.layout.room_label(t.room or "", "it") if t.room else ""
            text = f"{label} - {room}" if room else label
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            x0, y0 = int(x - tw / 2), int(y - 14)
            cv2.rectangle(img, (x0 - 3, y0 - th - 3), (x0 + tw + 3, y0 + 4), (30, 30, 30), -1)
            cv2.putText(img, text, (x0, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    # ------------------------------------------------------------ dataset
    def capture(self, count: int = 1) -> dict[str, Any]:
        frames = [self.frame] if count <= 1 or self.grab is None else self.grab(count)
        saved = 0
        for f in frames:
            if f is None:
                continue
            f = self._fit(f)
            if f is not self.frame:
                self.feed(f)
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
            img = (self.privacy or self._nominal_privacy).apply(f)
            cv2.imwrite(str(self.dataset_dir / f"{stamp}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            labels = self._labels()
            (self.dataset_dir / f"{stamp}.json").write_text(json.dumps(labels))
            saved += 1
        return {"ok": saved > 0, "message": f"{saved} immagini salvate", "message_en": f"{saved} images saved",
                "count": saved}

    def _labels(self) -> list[dict[str, Any]]:
        """Automatic labels: the boxes of the blobs, with the category of their track."""
        out = []
        names = {i.id: i.name for i in self.identities}
        for o in self.observations:
            if o.hand:
                continue
            best, best_d = None, 60.0
            for t in self.tracks:
                d = float(np.hypot(t.x - o.centroid_mm[0], t.y - o.centroid_mm[1]))
                if d < best_d:
                    best, best_d = t, d
            cat = best.category if best else o.category_guess
            out.append({"bbox": list(o.bbox), "category": cat,
                        "name": names.get(best.identity or "") if best else None})
        return out

    def export(self) -> dict[str, Any]:
        """The captures as a zip, with COCO and YOLO annotations."""
        images = sorted(self.dataset_dir.glob("*.jpg"))
        if not images:
            return {"ok": False, "error": "nothing captured yet"}
        out = self.dataset_dir.parent / "domotiq-dataset.zip"
        coco = {"images": [], "annotations": [], "categories": [{"id": i + 1, "name": c}
                                                                 for i, c in enumerate(COCO_CLASSES)]}
        ann_id = 1
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("yolo/classes.txt", "\n".join(COCO_CLASSES) + "\n")
            for n, path in enumerate(images, 1):
                img = cv2.imread(str(path))
                if img is None:
                    continue
                h, w = img.shape[:2]
                z.write(path, f"images/{path.name}")
                coco["images"].append({"id": n, "file_name": path.name, "width": w, "height": h})
                try:
                    labels = json.loads(path.with_suffix(".json").read_text())
                except (OSError, ValueError):
                    labels = []
                lines = []
                for lab in labels:
                    x, y, bw, bh = lab["bbox"]
                    cat = lab["category"] if lab["category"] in COCO_CLASSES else "object"
                    cid = COCO_CLASSES.index(cat)
                    coco["annotations"].append({"id": ann_id, "image_id": n, "category_id": cid + 1,
                                                "bbox": [x, y, bw, bh], "area": bw * bh, "iscrowd": 0,
                                                "attributes": {"name": lab.get("name")}})
                    ann_id += 1
                    lines.append(f"{cid} {(x + bw / 2) / w:.6f} {(y + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}")
                z.writestr(f"yolo/labels/{path.stem}.txt", "\n".join(lines) + ("\n" if lines else ""))
            z.writestr("coco/annotations.json", json.dumps(coco, indent=1))
        return {"ok": True, "path": str(out)}

    def clear_dataset(self) -> dict[str, Any]:
        shutil.rmtree(self.dataset_dir, ignore_errors=True)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        return {"ok": True}

    # ------------------------------------------------------------ recordings
    def start_recording(self, seconds: float = 60.0) -> dict[str, Any]:
        name = time.strftime("rec-%Y%m%d-%H%M%S")
        d = self.recordings_dir / name
        d.mkdir(parents=True, exist_ok=True)
        self._record = {"dir": d, "until": time.time() + max(5.0, min(seconds, 600.0)), "n": 0,
                        "log": open(d / "detections.jsonl", "w")}
        if self.calib:
            self.calib.save(d / "calibration.json")
        if self.segmenter and self.segmenter.reference_bgr is not None:
            ref = np.clip(self.segmenter.reference_bgr, 0, 255).astype(np.uint8)
            cv2.imwrite(str(d / "reference.jpg"), (self.privacy or self._nominal_privacy).apply(ref),
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
        return {"ok": True, "message": f"Registro {int(seconds)} s in {name}",
                "message_en": f"Recording {int(seconds)} s into {name}", "name": name}

    def _record_frame(self, small: np.ndarray, now: float) -> None:
        rec = self._record
        if now > rec["until"]:
            rec["log"].close()
            self._record = None
            return
        rec["n"] += 1
        img = (self.privacy or self._nominal_privacy).apply(small)
        cv2.imwrite(str(rec["dir"] / f"{rec['n']:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        rec["log"].write(json.dumps({
            "t": round(now, 3), "frame": rec["n"],
            "observations": [{"centroid": [round(v, 1) for v in o.centroid_mm], "bbox": list(o.bbox),
                              "area": round(o.area_mm2), "hand": o.hand, "guess": o.category_guess}
                             for o in self.observations],
            "tracks": [t.to_dict() for t in self.tracks],
        }) + "\n")
