# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the images that leave the board do not show.

Every image that goes out (live view, snapshots, dataset exports) passes
through here:
- everything around the house (the stand, the visitors, their phones) is
  blurred, once the house knows where the base is;
- the bathroom is blurred too, unless it is turned off in the settings:
  the footprint of each private room seen at floor level and at the top of
  its walls, plus a margin, so nothing inside shows whatever its height.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..layout import Layout
from .geometry import Calibration

WALL_TOP_MM = 135.0
MARGIN_MM = 12.0


def _hull(calib: Calibration, x0: float, x1: float, y0: float, y1: float, h: float) -> np.ndarray:
    pts = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)
    img = np.vstack([calib.image_of(pts, 0.0), calib.image_of(pts, h)])
    return cv2.convexHull(img.astype(np.float32)).reshape(-1, 2)


class Privacy:
    def __init__(self, layout: Layout, calib: Calibration, margin_mm: float = MARGIN_MM, private: bool = True,
                 outside: bool = False) -> None:
        self.size = (calib.width, calib.height)
        polys = []
        if private:
            m = margin_mm
            for room in layout.rooms.values():
                if room.private:
                    r = room.rect
                    polys.append(_hull(calib, r.x0 - m, r.x1 + m, r.y0 - m, r.y1 + m, WALL_TOP_MM + 10))
        self.mask = np.zeros((calib.height, calib.width), np.uint8)
        for p in polys:
            cv2.fillPoly(self.mask, [np.round(p).astype(np.int32)], 255)
        if outside:
            # the base and its walls up to their tops, seen from the camera: everything else is blurred
            b = layout.base
            house = np.zeros_like(self.mask)
            cv2.fillPoly(house, [np.round(_hull(calib, b.x0 - 3, b.x1 + 3, b.y0 - 3, b.y1 + 3, WALL_TOP_MM)).astype(np.int32)],
                         255)
            self.mask |= cv2.bitwise_not(house)
        ys, xs = np.nonzero(self.mask)
        self.box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None
        self._scaled: dict[tuple[int, int], tuple[np.ndarray, tuple[int, int, int, int]]] = {}

    def _for(self, w: int, h: int) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
        if self.box is None:
            return None
        if (w, h) == self.size:
            return self.mask, self.box
        if (w, h) not in self._scaled:
            m = cv2.resize(self.mask, (w, h), interpolation=cv2.INTER_NEAREST)
            sx, sy = w / self.size[0], h / self.size[1]
            x0, y0, x1, y1 = self.box
            self._scaled[(w, h)] = (m, (int(x0 * sx), int(y0 * sy), int(np.ceil(x1 * sx)), int(np.ceil(y1 * sy))))
        return self._scaled[(w, h)]

    def apply(self, img: np.ndarray) -> np.ndarray:
        found = self._for(img.shape[1], img.shape[0])
        if found is None:
            return img.copy()                # always a copy: callers draw on it
        mask, (x0, y0, x1, y1) = found
        out = img.copy()
        roi = out[y0:y1, x0:x1]
        # a heavy blur of a small copy: cheap on the board and nothing recognizable remains
        small = cv2.resize(roi, (max(1, (x1 - x0) // 12), max(1, (y1 - y0) // 12)), interpolation=cv2.INTER_AREA)
        blurred = cv2.resize(cv2.GaussianBlur(small, (5, 5), 0), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
        m = mask[y0:y1, x0:x1] > 0
        roi[m] = blurred[m]
        return out
