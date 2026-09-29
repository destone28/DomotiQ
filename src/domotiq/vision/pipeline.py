# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""From one frame to the things on the floor.

The house knows what it looks like empty (the reference, with the furniture
in place), so whatever differs from it is a figurine, the car, an object or
a visitor's hand. The comparison is done in Lab, after a correction of the
light:

- the lights of the house and of the fair hall change brightness and tint.
  Each pixel is corrected with the gains of the light of its own room (a
  gain per colour channel, estimated on the free floor of the room: the most
  common ratio to the reference, so a figurine or the car does not bias it,
  and the one closest to the previous frame when two are possible);
- a shadow is darker but keeps the colour of the floor: it does not count;
- zones that are not the floor (wall lights, the tree top, the camera pole)
  are masked, projected at the height where they really are, and so are the
  tops of the walls, where nothing can stand and the light of two rooms mixes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..layout import Circle, Layout
from .geometry import Calibration
from .scene import StaticScene, circle_pts, rect_pts
from .signature import signature

CATEGORY_HEIGHT = {"person": 90.0, "dog": 35.0, "cat": 35.0, "animal": 35.0, "car": 70.0, "object": 40.0}


@dataclass
class Observation:
    center_px: tuple[float, float]
    bbox: tuple[int, int, int, int]
    centroid_mm: tuple[float, float]
    near_mm: tuple[float, float]           # the point of the blob closest to the point under the camera
    far_mm: tuple[float, float]            # the farthest one
    area_mm2: float
    width_mm: float                        # across the direction to the point under the camera
    elongation: float                      # major / minor axis of the blob on the floor
    sig: np.ndarray
    border: bool = False
    hand: bool = False
    pixels: int = 0
    height_est: float | None = None
    category_guess: str = "object"
    extra: dict = field(default_factory=dict)

    def position(self, calib: Calibration, category: str | None) -> tuple[float, float]:
        """Where it stands on the floor.

        A figurine seen from above shows its top and the side facing the
        camera: the closest point of the blob is the front of its feet, the
        farthest is the back of its head. Brought down by its height, the
        head gives the feet too. The two estimates agree unless the feet
        are hidden behind a wall; then the head alone counts.
        """
        h = CATEGORY_HEIGHT.get(category or self.category_guess, 50.0)
        if (category or self.category_guess) == "car" or self.area_mm2 > 6000:
            # a box, not a figurine: the middle of what is seen, at half its height
            x, y = calib.lowered(np.array([self.centroid_mm]), h / 2)[0]
            return float(x), float(y)
        cx, cy, hc = calib.camera
        k = hc / max(hc - h, 1.0)
        c = np.array([cx, cy])
        cen = np.array(self.centroid_mm) - c
        rc = float(np.hypot(*cen))
        u = cen / rc if rc > 1e-6 else np.array([1.0, 0.0])
        rho = min(self.width_mm / (2 * k), 40.0)
        r_near = float(np.hypot(*(np.array(self.near_mm) - c)))
        r_far = float(np.hypot(*(np.array(self.far_mm) - c)))
        from_feet = r_near + rho
        from_head = r_far / k - rho
        if rc < rho * 1.5:
            r = rc / k                              # right under the camera: only the top is seen
        elif abs(from_feet - from_head) < 14.0:
            r = 0.5 * (from_feet + from_head)
        else:
            r = from_head
        x, y = c + u * max(r, 0.0)
        return float(x), float(y)


class Segmenter:
    def __init__(self, layout: Layout, calib: Calibration) -> None:
        self.layout = layout
        self.calib = calib
        self.w, self.h = calib.width, calib.height
        self.reference: np.ndarray | None = None       # Lab float32
        self.reference_bgr: np.ndarray | None = None   # float32, 0..255
        self.fg_prev: np.ndarray | None = None
        self.gains: dict[str, tuple[float, float, float]] = {}
        self._prev_gains: np.ndarray | None = None
        self._changed: dict[int, float] = {}          # region -> until when its light is changing
        self._crowded: dict[int, float] = {}          # region -> since when it is all foreground
        self.params = {"dc": 11.0, "dl": 20.0, "shadow_dc": 7.0, "min_px": 80, "hand_mm2": 3500.0}
        self.scene = StaticScene(layout, calib)
        self._build_masks()

    # ------------------------------------------------------------ masks
    def _poly_mask(self, polys: list[np.ndarray]) -> np.ndarray:
        m = np.zeros((self.h, self.w), np.uint8)
        for p in polys:
            cv2.fillPoly(m, [np.round(p).astype(np.int32)], 255)
        return m

    def _raised_hull(self, pts_mm: np.ndarray, h0: float, h1: float) -> np.ndarray:
        img = np.vstack([self.calib.image_of(pts_mm, h0), self.calib.image_of(pts_mm, h1)])
        return cv2.convexHull(img.astype(np.float32)).reshape(-1, 2)

    def _build_masks(self) -> None:
        lay, cal, scene = self.layout, self.calib, self.scene
        # the floor that matters: the base, with room on the right for the car coming in
        b = lay.base
        self.view_mask = self._poly_mask([cal.image_of(rect_pts([b.x0 - 15, b.x1 + 95, b.y0 - 15, b.y1 + 10]))])
        self.base_mask = self._poly_mask([cal.image_of(rect_pts([b.x0, b.x1, b.y0, b.y1]))])
        heights = {"pole": (0.0, 900.0), "tree-canopy": (95.0, 170.0)}
        polys = []
        for raw, shape in zip(lay.raw.get("excluded", []), lay.excluded):
            h0, h1 = heights.get(raw["id"], (100.0, 135.0))         # wall lights sit 100-135 mm up
            pts = circle_pts(shape.cx, shape.cy, shape.r) if isinstance(shape, Circle) \
                else rect_pts([shape.x0, shape.x1, shape.y0, shape.y1])
            polys.append(self._raised_hull(pts, h0, h1))
        excluded = cv2.dilate(self._poly_mask(polys), np.ones((5, 5), np.uint8))
        walls = (scene.kind == StaticScene.KINDS["wall"]) | (scene.kind == StaticScene.KINDS["fence"])
        wall_tops = (walls & scene.top).astype(np.uint8) * 255
        pole = (scene.kind == StaticScene.KINDS["pole"]).astype(np.uint8) * 255
        excluded |= cv2.dilate(wall_tops, np.ones((3, 3), np.uint8)) | cv2.dilate(pole, np.ones((5, 5), np.uint8))
        self.mask = cv2.bitwise_and(self.view_mask, cv2.bitwise_not(excluded))
        # the rim of what is analysed: arms reach the house across it, the car only at its gate
        inner = cv2.erode(self.view_mask, np.ones((7, 7), np.uint8))
        self.rim = (self.view_mask > 0) & (inner == 0)
        gates = np.zeros((self.h, self.w), np.uint8)
        for d in lay.doors:
            if d.vehicles:
                r = d.rect
                pts = rect_pts([r.x0 - 10, r.x1 + 120, r.y0 - 15, r.y1 + 15])
                cv2.fillPoly(gates, [np.round(self._raised_hull(pts, 0.0, 80.0)).astype(np.int32)], 255)
        self.gate = gates > 0
        # which light each pixel is under: the room of the surface it shows, mixed across doorways
        self.label, self.label_b, self.blend, self.region_names = scene.room_labels()
        self.blend3 = self.blend[..., None]
        # where each light is measured: the free floor of the room, away from furniture and walls
        free = (self.mask > 0) & (scene.z < 0.5) & (self.blend == 0)
        free = cv2.erode(free.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        self.samples = [np.flatnonzero(free & (self.label == i)) for i in range(len(self.region_names))]
        self.mm2_per_px = float(np.mean([cal.mm_per_px(x, y) for x, y in ((100, 100), (325, 145), (550, 300))])) ** 2

    # ------------------------------------------------------------ reference
    def set_reference(self, frames_bgr: list[np.ndarray]) -> None:
        stack = np.stack([self._fit(f).astype(np.float32) for f in frames_bgr])
        self.reference_bgr = np.median(stack, axis=0).astype(np.float32)
        self.reference = cv2.cvtColor(self.reference_bgr / 255.0, cv2.COLOR_BGR2LAB)
        self.fg_prev = None
        self._prev_gains = None
        self.gains = {}

    def update_reference(self, frame_bgr: np.ndarray, fg: np.ndarray, rate: float = 0.02) -> None:
        """Follow slow changes of the hall light where nothing stands."""
        if self.reference_bgr is None:
            return
        still = (cv2.dilate(fg, np.ones((9, 9), np.uint8)) == 0) & (self.mask > 0)
        # the reference is kept under the light it was taken with: bring the frame back to it
        cur = self.corrected(self._fit(frame_bgr), update=False)
        self.reference_bgr[still] += rate * (cur[still] - self.reference_bgr[still])
        self.reference = cv2.cvtColor(self.reference_bgr / 255.0, cv2.COLOR_BGR2LAB)

    def _fit(self, frame: np.ndarray) -> np.ndarray:
        if frame.shape[1] != self.w or frame.shape[0] != self.h:
            return cv2.resize(frame, (self.w, self.h), interpolation=cv2.INTER_AREA)
        return frame

    # ------------------------------------------------------------ light correction
    def light_changed(self, rooms: list[str], now: float, seconds: float = 1.5) -> None:
        """The house changed the light of these rooms: their gain is measured afresh."""
        for room in rooms:
            if room in self.region_names:
                self._changed[self.region_names.index(room)] = now + seconds

    def _gains(self, cur: np.ndarray, update: bool = True, now: float = 0.0) -> np.ndarray:
        if not update and self._prev_gains is not None:
            return self._prev_gains
        ref = self.reference_bgr.reshape(-1, 3)
        flat = cur.reshape(-1, 3)
        busy = None
        if self.fg_prev is not None:
            busy = cv2.dilate(self.fg_prev, np.ones((7, 7), np.uint8)).ravel() > 0
        n = len(self.samples)
        prev = self._prev_gains if self._prev_gains is not None else np.ones((n, 3), np.float32)
        gains = np.full((n, 3), np.nan, np.float32)
        for i, idx in enumerate(self.samples):
            if busy is not None and len(idx):
                free = idx[~busy[idx]]
                # almost all foreground for a while: the light changed under it, measure again
                if len(free) < 0.15 * len(idx):
                    since = self._crowded.setdefault(i, now)
                    if now - since > 3.0:
                        free = idx
                        self._crowded.pop(i, None)
                else:
                    self._crowded.pop(i, None)
                idx = free
            if len(idx) > 3000:
                idx = idx[:: len(idx) // 3000]
            if len(idx) < 50:
                continue
            c, r = flat[idx], ref[idx]
            ok = r.min(axis=1) > 12
            c, r = c[ok], r[ok]
            if len(c) < 50:
                continue
            lr = np.log((c.sum(axis=1) + 3) / (r.sum(axis=1) + 3))
            hist, edges = np.histogram(lr, bins=60, range=(-1.2, 1.2))
            centres = 0.5 * (edges[:-1] + edges[1:])
            # the peak nearest to the previous light, if it is still a real peak
            last = float(np.log(prev[i].mean()))
            around = np.abs(centres - last) <= 0.08
            fresh = self._changed.get(i, 0.0) > now
            if not fresh and around.any() and hist[around].sum() >= max(60, 0.06 * len(lr)):
                k = int(np.flatnonzero(around)[np.argmax(hist[around])])
            else:
                k = int(np.argmax(hist))
            near = np.abs(lr - centres[k]) < 0.05
            if near.sum() < 25:
                continue
            cn, rn = c[near], r[near]
            for ch in range(3):
                unsat = cn[:, ch] < 250
                if unsat.sum() >= 25:
                    gains[i, ch] = np.median((cn[unsat, ch] + 1) / (rn[unsat, ch] + 1))
                else:
                    # the floor saturates in this channel: the gain is at least this much
                    gains[i, ch] = np.median(255.0 / (rn[:, ch] + 1))
        valid = ~np.isnan(gains[:, 0])
        # a region with no free floor in sight keeps its last light, or takes the median of the others
        fallback = np.median(gains[valid], axis=0) if valid.any() else np.ones(3, np.float32)
        for i in np.flatnonzero(~valid):
            gains[i] = prev[i] if self._prev_gains is not None else fallback
        gains = np.clip(gains, 0.3, 3.0)
        self._prev_gains = gains
        self.gains = {nm: tuple(round(float(v), 3) for v in g) for nm, g in zip(self.region_names, gains)}
        return gains

    def corrected(self, frame_bgr: np.ndarray, update: bool = True, now: float = 0.0) -> np.ndarray:
        cur = frame_bgr.astype(np.float32)
        gains = self._gains(cur, update, now)
        g = gains[self.label] * (1.0 - self.blend3) + gains[self.label_b] * self.blend3
        out = cur / g
        # a saturated channel carries no information: take the reference where it would saturate too
        sat = (cur >= 250) & (self.reference_bgr * g >= 235)
        out[sat] = self.reference_bgr[sat]
        return np.clip(out, 0, 255)

    # ------------------------------------------------------------ segmentation
    def foreground(self, frame_bgr: np.ndarray, now: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        p = self.params
        cur = cv2.cvtColor(self.corrected(frame_bgr, True, now) / 255.0, cv2.COLOR_BGR2LAB)
        ref = self.reference
        dl = cur[..., 0] - ref[..., 0]
        dc = np.sqrt((cur[..., 1] - ref[..., 1]) ** 2 + (cur[..., 2] - ref[..., 2]) ** 2)
        shadow = (dl < 0) & (dc < p["shadow_dc"])
        fg = ((dc > p["dc"]) | ((np.abs(dl) > p["dl"]) & ~shadow)).astype(np.uint8) * 255
        fg = cv2.bitwise_and(fg, self.mask)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        return fg, cur

    def process(self, frame_bgr: np.ndarray, now: float | None = None
                ) -> tuple[list[Observation], np.ndarray, np.ndarray | None]:
        frame_bgr = self._fit(frame_bgr)
        if self.reference is None:
            return [], np.zeros((self.h, self.w), np.uint8), None
        fg, lab = self.foreground(frame_bgr, time.time() if now is None else now)
        self.fg_prev = fg
        return self.blobs(fg, lab), fg, lab

    def blobs(self, fg: np.ndarray, lab: np.ndarray) -> list[Observation]:
        n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
        obs: list[Observation] = []
        cal = self.calib
        c = np.array(cal.nadir)
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if area < self.params["min_px"]:
                continue
            blob = labels[y:y + h, x:x + w] == i
            ys, xs = np.nonzero(blob)
            pts_px = np.column_stack([xs + x, ys + y]).astype(np.float64)
            floor = cal.to_floor(pts_px[:: max(1, len(pts_px) // 500)])
            rel = floor - c
            r = np.hypot(rel[:, 0], rel[:, 1])
            near, far = floor[int(np.argmin(r))], floor[int(np.argmax(r))]
            centroid_mm = cal.to_floor(np.array([centroids[i]]))[0]
            d = centroid_mm - c
            u = d / (np.hypot(*d) + 1e-6)
            across = rel @ np.array([-u[1], u[0]])
            width = float(across.max() - across.min())
            cov = np.cov(floor.T) if len(floor) > 3 else np.eye(2)
            ev = np.sort(np.linalg.eigvalsh(cov))
            elong = float(np.sqrt(ev[1] / max(ev[0], 1e-6)))
            area_mm2 = float(area) * self.mm2_per_px
            border = x <= 1 or y <= 1 or x + w >= self.w - 1 or y + h >= self.h - 1
            on_rim = blob & self.rim[y:y + h, x:x + w]
            rim_px = int(on_rim.sum())
            at_gate = rim_px > 0 and int((on_rim & self.gate[y:y + h, x:x + w]).sum()) > 0.8 * rim_px
            hand = (rim_px >= 6 or border) and area_mm2 > 1500 and not at_gate
            sub = lab[y:y + h, x:x + w][blob]
            ref = self.reference[y:y + h, x:x + w][blob]
            # keep the pixels that differ most from the floor: the edges of a blob mix both
            dcol = np.hypot(sub[:, 1] - ref[:, 1], sub[:, 2] - ref[:, 2]) + np.abs(sub[:, 0] - ref[:, 0]) * 0.3
            keep = sub[dcol >= np.percentile(dcol, 35)] if len(sub) > 20 else sub
            r_near, r_far = float(r.min()), float(r.max())
            h_est = None
            if r_far > 130:
                # a vertical thing seen from above stretches away from the point under the camera
                k = 1.0 + max(0.0, (r_far - r_near) - width) / max(r_near, 1.0)
                h_est = float(cal.camera[2] * (1.0 - 1.0 / k))
            if area_mm2 > 6000:
                guess = "car"
            elif h_est is not None and h_est >= 55 and width < 45:
                guess = "person"
            elif h_est is None and 250 < area_mm2 < 1600 and elong < 1.8:
                guess = "person"             # near the centre a figurine is just its top: most are people
            elif elong > 1.8 and area_mm2 < 3000 and (h_est is None or h_est < 55):
                guess = "animal"
            else:
                guess = "object"
            o = Observation((float(centroids[i][0]), float(centroids[i][1])), (int(x), int(y), int(w), int(h)),
                            (float(centroid_mm[0]), float(centroid_mm[1])), (float(near[0]), float(near[1])),
                            (float(far[0]), float(far[1])), area_mm2, width, elong, signature(keep),
                            border, hand, int(area), h_est, guess)
            o.extra["label"] = i
            obs.append(o)
        self._join_hands(obs, labels)
        return obs

    def _join_hands(self, obs: list[Observation], labels: np.ndarray) -> None:
        """An arm crossing a wall top is cut in two: a large blob touching a hand is the same hand."""
        for _ in range(3):
            hands = [o.extra["label"] for o in obs if o.hand]
            if not hands:
                return
            near_hand = cv2.dilate(np.isin(labels, hands).astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
            changed = False
            for o in obs:
                if o.hand or o.area_mm2 < 1200:
                    continue
                x, y, w, h = o.bbox
                if (near_hand[y:y + h, x:x + w] & (labels[y:y + h, x:x + w] == o.extra["label"])).any():
                    o.hand = True
                    changed = True
            if not changed:
                return
