# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The bathroom never leaves the board in focus.

Every image that goes out (live view, snapshots, dataset exports) passes
through here. The blurred area is the footprint of each private room seen at
floor level and at the top of its walls, plus a margin, so nothing inside
shows whatever its height.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..layout import Layout
from .geometry import Calibration

WALL_TOP_MM = 135.0
MARGIN_MM = 12.0


class Privacy:
    def __init__(self, layout: Layout, calib: Calibration) -> None:
        self.size = (calib.width, calib.height)
        polys = []
        for room in layout.rooms.values():
            if not room.private:
                continue
            r = room.rect
            pts = np.array([[r.x0 - MARGIN_MM, r.y0 - MARGIN_MM], [r.x1 + MARGIN_MM, r.y0 - MARGIN_MM],
                            [r.x1 + MARGIN_MM, r.y1 + MARGIN_MM], [r.x0 - MARGIN_MM, r.y1 + MARGIN_MM]])
            img = np.vstack([calib.image_of(pts, 0.0), calib.image_of(pts, WALL_TOP_MM + 10)])
            polys.append(cv2.convexHull(img.astype(np.float32)).reshape(-1, 2))
        self.mask = np.zeros((calib.height, calib.width), np.uint8)
        for p in polys:
            cv2.fillPoly(self.mask, [np.round(p).astype(np.int32)], 255)
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
            return img
        mask, (x0, y0, x1, y1) = found
        out = img.copy()
        roi = out[y0:y1, x0:x1]
        # a heavy blur of a small copy: cheap on the board and nothing recognizable remains
        small = cv2.resize(roi, (max(1, (x1 - x0) // 12), max(1, (y1 - y0) // 12)), interpolation=cv2.INTER_AREA)
        blurred = cv2.resize(cv2.GaussianBlur(small, (5, 5), 0), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
        m = mask[y0:y1, x0:x1] > 0
        roi[m] = blurred[m]
        return out
