# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Synthetic webcam frames of the house, for tests and for tuning at the desk.

A small renderer of the diorama seen from the camera on the pole: floor,
lawns, walls, fences and furniture as extruded shapes, figurines as coloured
cylinders, animals and the car as boxes, a visitor's hand as a large blob
coming from the edge of the image, with the occlusions of the real camera
(a figurine behind a wall is partly hidden, one in front of it covers it).

The lights of the rooms tint what stands in them, the hall light can change
brightness and tint, and there is sensor noise. It is not meant to look
real, only to exercise the same geometry and the same difficulties as the
real camera.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..layout import Layout
from .geometry import Calibration
from .scene import Raster, circle_pts, rect_pts, static_prisms


def hex_bgr(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[4:6], 16), int(c[2:4], 16), int(c[0:2], 16)


@dataclass
class Thing:
    x: float
    y: float
    color: str = "#d03030"
    kind: str = "person"              # person, animal, car, object
    height: float = 90.0
    radius: float = 11.0
    length: float = 0.0               # animals and cars: size along x
    width: float = 0.0


@dataclass
class Hand:
    """A hand coming in from an image edge towards a floor point, `height` above the floor."""
    x: float
    y: float
    side: str = "bottom"              # which edge of the image the arm comes from
    height: float = 150.0
    color: str = "#e0ac8a"


FLOOR = "#a3a19c"
DRIVEWAY = "#8c8a86"
LAWN = "#5e9a4e"
PATH = "#c8bfae"
OUTSIDE = "#4a4d52"


class Renderer:
    def __init__(self, layout: Layout, calib: Calibration | None = None, seed: int = 0) -> None:
        self.layout = layout
        self.calib = calib or Calibration.synthetic()
        self.rng = np.random.default_rng(seed)
        self.raster = Raster(self.calib)
        self._static = [(base, h, hex_bgr(color)) for base, h, color, _ in static_prisms(layout)]
        self._empty: tuple[np.ndarray, np.ndarray] | None = None

    # ------------------------------------------------------------ drawing
    def _flat(self, img: np.ndarray, poly: np.ndarray, color: str) -> None:
        cv2.fillPoly(img, [np.round(self.calib.image_of(poly)).astype(np.int32)], hex_bgr(color), cv2.LINE_AA)

    def _prism(self, img: np.ndarray, z: np.ndarray, base: np.ndarray, h: float,
               color: tuple[int, int, int]) -> None:
        top = np.array(color, np.float32)

        def paint(y0, x0, ys, xs, face):
            if face is None:
                img[y0 + ys, x0 + xs] = color
            else:
                shade = 0.66 + 0.14 * abs(face[0])     # side faces darker, lit a little from the side
                img[y0 + ys, x0 + xs] = np.clip(top * shade, 0, 255).astype(np.uint8)

        self.raster.prism(z, base, h, paint)

    def _thing_prisms(self, t: Thing) -> list[tuple[np.ndarray, float, tuple[int, int, int]]]:
        color = hex_bgr(t.color)
        if t.kind == "person" or (t.kind == "object" and not t.length):
            out = [(circle_pts(t.x, t.y, t.radius, 20), t.height, color)]
            if t.kind == "person":
                # a slightly lighter head, as the printed figurines have
                lighter = tuple(min(255, int(c * 1.1) + 8) for c in color)
                out.append((circle_pts(t.x, t.y, t.radius * 0.7, 16), t.height + 2, lighter))
            return out
        L, W = t.length or 60.0, t.width or 22.0
        return [(rect_pts([t.x - L / 2, t.x + L / 2, t.y - W / 2, t.y + W / 2]), t.height, color)]

    def _shadow(self, img: np.ndarray, z: np.ndarray, t: Thing) -> None:
        if t.kind == "person" or not t.length:
            base = circle_pts(t.x + 12, t.y - 9, t.radius * 1.2, 20)
        else:
            L, W = t.length or 60.0, t.width or 22.0
            base = rect_pts([t.x - L / 2 + 10, t.x + L / 2 + 10, t.y - W / 2 - 8, t.y + W / 2 - 8])
        m = np.zeros(z.shape, np.uint8)
        cv2.fillPoly(m, [np.round(self.calib.image_of(base)).astype(np.int32)], 255, cv2.LINE_AA)
        m = cv2.GaussianBlur(m, (7, 7), 0).astype(np.float32) / 255.0 * (z <= 0.5)
        img[:] = np.clip(img.astype(np.float32) * (1.0 - 0.3 * m[..., None]), 0, 255).astype(np.uint8)

    def _hand(self, img: np.ndarray, h: Hand) -> None:
        cal = self.calib
        tip = cal.image_of(np.array([[h.x, h.y]]), h.height)[0]
        Hh, Ww = img.shape[:2]
        start = {"bottom": (tip[0], Hh + 40), "top": (tip[0], -40), "left": (-40, tip[1]),
                 "right": (Ww + 40, tip[1])}[h.side]
        scale = cal.camera[2] / max(cal.camera[2] - h.height, 1.0) / cal.mm_per_px(h.x, h.y)
        thick = int(max(8, 45 * scale))
        color = hex_bgr(h.color)
        cv2.line(img, (int(start[0]), int(start[1])), (int(tip[0]), int(tip[1])), color, thick, cv2.LINE_AA)
        cv2.circle(img, (int(tip[0]), int(tip[1])), int(thick * 0.8), color, -1, cv2.LINE_AA)

    def _floor(self) -> tuple[np.ndarray, np.ndarray]:
        if self._empty is None:
            cal = self.calib
            lay = self.layout.raw
            img = np.full((cal.height, cal.width, 3), hex_bgr(OUTSIDE), np.uint8)
            b = lay["base"]
            self._flat(img, rect_pts(b), FLOOR)
            self._flat(img, rect_pts([b[0], b[1], b[2], 0]), DRIVEWAY)
            for lawn in lay["lawns"]:
                self._flat(img, rect_pts(lawn), LAWN)
            self._flat(img, rect_pts(lay["path"]), PATH)
            self._empty = (img, np.zeros((cal.height, cal.width), np.float32))
        img, z = self._empty
        return img.copy(), z.copy()

    def _lights(self, img: np.ndarray, z: np.ndarray, lights: dict[str, tuple[str, float]]) -> np.ndarray:
        """A room light tints every surface in its room, fading across the thickness of the walls."""
        surface = self.raster.surface_xy(z)
        gain_map = np.ones(img.shape, np.float32)
        for room_id, (color, level) in lights.items():
            room = self.layout.rooms.get(room_id)
            if not room or level <= 0:
                continue
            r = room.rect
            dx = np.maximum(np.maximum(r.x0 - surface[..., 0], surface[..., 0] - r.x1), 0)
            dy = np.maximum(np.maximum(r.y0 - surface[..., 1], surface[..., 1] - r.y1), 0)
            w = np.clip(1.0 - np.hypot(dx, dy) / 10.0, 0.0, 1.0)[..., None]
            tint = np.array(hex_bgr(color), np.float32) / 255.0
            gain = 1.0 + level * (0.25 + 0.35 * tint)
            gain_map = np.maximum(gain_map, 1.0 + w * (gain - 1.0))
        return gain_map

    # ------------------------------------------------------------ frame
    def render(self, things: list[Thing] | None = None, *, hands: list[Hand] | None = None,
               lights: dict[str, tuple[str, float]] | None = None, brightness: float = 1.0,
               cast: tuple[float, float, float] = (1.0, 1.0, 1.0), noise: float = 2.0,
               shadows: bool = True) -> np.ndarray:
        img, z = self._floor()
        things = things or []
        if shadows:
            for t in things:
                self._shadow(img, z, t)
        prisms = list(self._static)
        for t in things:
            prisms += self._thing_prisms(t)
        for base, h, color in prisms:
            self._prism(img, z, base, h, color)
        gain = self._lights(img, z, lights) if lights else 1.0
        for h in hands or []:
            self._hand(img, h)
        # every light adds up on the sensor, which saturates only once
        f = img.astype(np.float32) * gain * brightness * np.array(cast, np.float32)
        if noise:
            f += self.rng.normal(0, noise, f.shape).astype(np.float32)
        img = np.clip(f, 0, 255).astype(np.uint8)
        return cv2.GaussianBlur(img, (3, 3), 0)


class SyntheticCamera:
    """Stands in for the webcam: the empty house, then figurines walking from room to room.

    Same interface as `camera.Camera`, so the whole vision process can run on
    a PC without a webcam (``domotiq --camera synthetic``).
    """

    PATHS = [
        ("#d03030", [(100, 60), (100, 150), (200, 110), (300, 100), (380, 150), (300, 60), (200, 110), (100, 60)]),
        ("#3050d0", [(520, 60), (520, 180), (390, 175), (300, 165), (330, 60), (300, 165), (390, 175), (520, 180),
                     (520, 60)]),
    ]

    def __init__(self, layout: Layout, fps: float = 10.0, empty_s: float = 4.0) -> None:
        import threading

        self.renderer = Renderer(layout, seed=7)
        self.fps = fps
        self.empty_s = empty_s
        self.device = "synthetic"
        self.size = (self.renderer.calib.width, self.renderer.calib.height)
        self.controls = None
        self.reconnects = 0
        self.on_connect = None
        self._seq = 0
        self._frame: np.ndarray | None = None
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._t0 = 0.0
        self._thread = threading.Thread(target=self._run, name="synthetic-camera", daemon=True)

    @property
    def connected(self) -> bool:
        return self._frame is not None

    def corners_fraction(self) -> list[list[float]]:
        w, h = self.size
        return [[u / w, v / h] for u, v in self.renderer.calib.corners]

    def _things(self, t: float) -> list[Thing]:
        if t < self.empty_s:
            return []
        out = []
        for color, pts in self.PATHS:
            seg_s = 4.0
            k = ((t - self.empty_s) / seg_s) % (len(pts) - 1)
            i = int(k)
            f = k - i
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            out.append(Thing(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, color))
        return out

    def _run(self) -> None:
        import time
        self._t0 = time.time()
        while not self._stop.is_set():
            img = self.renderer.render(self._things(time.time() - self._t0))
            with self._cv:
                self._frame = img
                self._seq += 1
                self._cv.notify_all()
            time.sleep(1.0 / self.fps)

    def start(self) -> bool:
        self._thread.start()
        return True

    def latest(self, after: int = -1, timeout: float = 1.0):
        with self._cv:
            if self._seq <= after:
                self._cv.wait(timeout)
            return self._seq, self._frame

    def flush(self, frames: int = 2, timeout: float = 2.0) -> None:
        seq, _ = self.latest()
        self.latest(seq + frames - 1, timeout)

    def stop(self) -> None:
        self._stop.set()
