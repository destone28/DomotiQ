# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The empty house as the camera sees it: what is at each pixel, and how high.

The layout gives walls and furniture as vertical prisms. Rasterized from the
camera, they give for each pixel the height of the surface it shows. Along
any ray of a camera looking down the closer point is the higher one, so the
highest surface wins, with no sorting.

From the height the point on the surface follows, and from that point the
room it belongs to: the face of a wall shows the room it faces, not the one
behind it, and each pixel is corrected with the light of the right room.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..layout import Layout
from .geometry import Calibration


def rect_pts(r) -> np.ndarray:
    x0, x1, y0, y1 = r
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def circle_pts(cx: float, cy: float, r: float, n: int = 24) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([cx + r * np.cos(a), cy + r * np.sin(a)])


def cut_doors(rect, doors) -> list[list[float]]:
    """A wall with its door openings removed (doors lie inside the wall thickness)."""
    x0, x1, y0, y1 = rect
    horizontal = (x1 - x0) >= (y1 - y0)
    pieces = [(x0, x1) if horizontal else (y0, y1)]
    for d in doors:
        dx0, dx1, dy0, dy1 = d
        if horizontal and dy0 >= y0 - 1 and dy1 <= y1 + 1 and dx1 > x0 and dx0 < x1:
            cut = (dx0, dx1)
        elif not horizontal and dx0 >= x0 - 1 and dx1 <= x1 + 1 and dy1 > y0 and dy0 < y1:
            cut = (dy0, dy1)
        else:
            continue
        nxt = []
        for a, b in pieces:
            if cut[1] <= a or cut[0] >= b:
                nxt.append((a, b))
                continue
            if cut[0] > a:
                nxt.append((a, cut[0]))
            if cut[1] < b:
                nxt.append((cut[1], b))
        pieces = nxt
    return [[a, b, y0, y1] if horizontal else [x0, x1, a, b] for a, b in pieces if b - a >= 0.5]


def static_prisms(layout: Layout) -> list[tuple[np.ndarray, float, str, str]]:
    """(footprint, height, colour, kind) of every wall piece and piece of furniture."""
    raw = layout.raw
    out = []
    doors = [d["rect"] for d in raw["doors"]]
    for w in raw["walls"]:
        kind = w.get("kind", "wall")
        for r in cut_doors(w["rect"], doors):
            out.append((rect_pts(r), float(w["height"]), "#9c7a55" if kind == "fence" else "#ecebe6", kind))
    for f in raw["furniture"]:
        shape = circle_pts(*f["circle"]) if "circle" in f else rect_pts(f["rect"])
        h = 880.0 if f["id"] == "pole" else float(f["height"])
        out.append((shape, h, f["color"], "pole" if f["id"] == "pole" else "furniture"))
    return out


class Raster:
    """Draws vertical prisms from the camera, keeping the highest surface at each pixel."""

    def __init__(self, calib: Calibration) -> None:
        self.calib = calib
        H, W = calib.height, calib.width
        ys, xs = np.mgrid[0:H, 0:W]
        pix = np.column_stack([xs.ravel() + 0.5, ys.ravel() + 0.5])
        self.floor_xy = calib.to_floor(pix).reshape(H, W, 2)

    def surface_xy(self, z: np.ndarray) -> np.ndarray:
        cx, cy, hc = self.calib.camera
        k = ((hc - z) / hc)[..., None]
        return np.array([cx, cy]) + (self.floor_xy - [cx, cy]) * k

    def prism(self, z: np.ndarray, base: np.ndarray, h: float, paint=None) -> None:
        """Raise the height buffer `z` with a prism; `paint(y0, x0, ys, xs, face)` colours the winners.

        `face` is None for the top, else the unit normal of the side face.
        """
        cal = self.calib
        cx, cy, hc = cal.camera
        H, W = z.shape
        bottom, top = cal.image_of(base, 0.0), cal.image_of(base, h)
        n = len(base)
        area = 0.5 * np.sum(base[:, 0] * np.roll(base[:, 1], -1) - np.roll(base[:, 0], -1) * base[:, 1])
        sign = 1.0 if area > 0 else -1.0
        centre = np.array([cx, cy])
        for i in range(n):
            j = (i + 1) % n
            a, b = base[i], base[j]
            normal = sign * np.array([b[1] - a[1], a[0] - b[0]])
            if normal @ (centre - a) <= 0:
                continue                       # a face turned away from the camera is not seen
            quad = np.array([bottom[i], bottom[j], top[j], top[i]])
            x0, y0 = np.floor(quad.min(axis=0)).astype(int)
            x1, y1 = np.ceil(quad.max(axis=0)).astype(int) + 1
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
            if x1 <= x0 or y1 <= y0:
                continue
            m = np.zeros((y1 - y0, x1 - x0), np.uint8)
            cv2.fillConvexPoly(m, np.round(quad - [x0, y0]).astype(np.int32), 1)
            sel = m > 0
            p = self.floor_xy[y0:y1, x0:x1][sel]
            den = (p - centre) @ normal
            with np.errstate(divide="ignore", invalid="ignore"):
                zz = hc * (1.0 + (normal @ (centre - a)) / den)
            zz = np.nan_to_num(np.clip(zz, 0.0, h), nan=0.0)
            zb = z[y0:y1, x0:x1]
            win = zz > zb[sel]
            idx = np.nonzero(sel)
            wy, wx = idx[0][win], idx[1][win]
            zb[wy, wx] = zz[win]
            if paint is not None and len(wy):
                paint(y0, x0, wy, wx, normal / (np.hypot(*normal) + 1e-9))
        pts = np.round(top).astype(np.int32)
        x0, y0 = np.maximum(pts.min(axis=0), 0)
        x1, y1 = np.minimum(pts.max(axis=0) + 1, [W, H])
        if x1 <= x0 or y1 <= y0:
            return
        m = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillPoly(m, [pts - [x0, y0]], 1)
        zb = z[y0:y1, x0:x1]
        win = (m > 0) & (h >= zb)
        zb[win] = h
        if paint is not None:
            wy, wx = np.nonzero(win)
            if len(wy):
                paint(y0, x0, wy, wx, None)


class StaticScene:
    """Height, kind and room of every pixel of the empty house."""

    KINDS = {"floor": 0, "wall": 1, "fence": 2, "furniture": 3, "pole": 4}

    def __init__(self, layout: Layout, calib: Calibration) -> None:
        self.layout = layout
        self.calib = calib
        self.raster = Raster(calib)
        H, W = calib.height, calib.width
        self.z = np.zeros((H, W), np.float32)
        self.kind = np.zeros((H, W), np.uint8)
        self.top = np.zeros((H, W), bool)             # the pixel shows the top of a prism
        for base, h, _color, kind in static_prisms(layout):
            code = self.KINDS[kind]

            def paint(y0, x0, ys, xs, face, code=code):
                self.kind[y0 + ys, x0 + xs] = code
                self.top[y0 + ys, x0 + xs] = face is None

            self.raster.prism(self.z, base, h, paint)
        self.surface = self.raster.surface_xy(self.z)

    def room_labels(self, blend_mm: float = 10.0) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
        """The light each pixel is under, as two regions and a weight.

        Inside a room the pixel belongs to that room alone. In the thickness
        of a wall between two rooms (a doorway, the garage gate) it takes a
        mix of the two, going from one to the other across the wall. The
        last region is everything outside the base.
        """
        rooms = list(self.layout.rooms.values())
        sx, sy = self.surface[..., 0], self.surface[..., 1]
        dist = np.empty((len(rooms) + 1,) + sx.shape, np.float32)
        for i, room in enumerate(rooms):
            r = room.rect
            dx = np.maximum(np.maximum(r.x0 - sx, sx - r.x1), 0)
            dy = np.maximum(np.maximum(r.y0 - sy, sy - r.y1), 0)
            dist[i] = np.hypot(dx, dy)
        b = self.layout.base
        inside = (sx > b.x0) & (sx < b.x1) & (sy > b.y0) & (sy < b.y1)
        to_edge = np.minimum.reduce([sx - b.x0, b.x1 - sx, sy - b.y0, b.y1 - sy])
        dist[-1] = np.where(inside, to_edge, 0.0)
        order = np.argsort(dist, axis=0)
        a, bb = order[0], order[1]
        da = np.take_along_axis(dist, a[None], 0)[0]
        db = np.take_along_axis(dist, bb[None], 0)[0]
        t = np.where(da + db <= blend_mm + 0.5, da / np.maximum(da + db, 1e-6), 0.0).astype(np.float32)
        return a.astype(np.int32), bb.astype(np.int32), t, [room.id for room in rooms] + ["outside"]
