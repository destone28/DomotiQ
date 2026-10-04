# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""From image pixels to millimetres on the floor, and back.

Four taps on the corners of the base give a homography between the image
and the floor plane. With the position of the camera (known from the CAD
model: above (325, 145), 930 mm over the floor) the same homography also
places points that are above the floor: a pinhole camera sees a point at
height h exactly where it would see the floor point on the same ray,

    A = C + (P - C) * H / (H - h)

so the head of an 90 mm figurine seen near a corner lands several
centimetres further from the centre than its feet. The feet are the point
of the figurine closest to the point under the camera.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

# corners of the base on the floor, in the order they are tapped
BASE_CORNERS_MM = [(0.0, -80.0), (650.0, -80.0), (650.0, 370.0), (0.0, 370.0)]


@dataclass
class Calibration:
    width: int = 640
    height: int = 480
    corners: list[list[float]] = field(default_factory=list)   # 4 image points, pixels of width x height
    camera: tuple[float, float, float] = (325.0, 145.0, 930.0)
    valid: bool = False

    def __post_init__(self) -> None:
        self._h: np.ndarray | None = None
        self._hinv: np.ndarray | None = None
        if self.valid and len(self.corners) == 4:
            self._compute()

    # ------------------------------------------------------------ building
    def _compute(self) -> None:
        src = np.array(BASE_CORNERS_MM, dtype=np.float64)
        dst = np.array(self.corners, dtype=np.float64)
        self._h, _ = cv2.findHomography(src, dst)
        self._hinv = np.linalg.inv(self._h)

    @classmethod
    def from_corners(cls, corners_frac: list[list[float]], width: int, height: int,
                     camera: tuple[float, float, float]) -> "Calibration":
        """Corners as fractions of the image (what the web app sends)."""
        pts = [[u * width, v * height] for u, v in corners_frac]
        c = cls(width, height, pts, camera, True)
        return c

    @classmethod
    def synthetic(cls, width: int = 640, height: int = 480, camera=(325.0, 145.0, 930.0),
                  view_mm: float = 725.0) -> "Calibration":
        """A camera looking straight down, as mounted on the pole (used by the simulator and tests)."""
        f = width * camera[2] / view_mm
        cx, cy = width / 2, height / 2
        pts = [[cx + f * (x - camera[0]) / camera[2], cy - f * (y - camera[1]) / camera[2]]
               for x, y in BASE_CORNERS_MM]
        return cls(width, height, pts, camera, True)

    def scaled(self, width: int, height: int) -> "Calibration":
        sx, sy = width / self.width, height / self.height
        return Calibration(width, height, [[u * sx, v * sy] for u, v in self.corners], self.camera, self.valid)

    # ------------------------------------------------------------ persistence
    def save(self, path: Path) -> None:
        d = asdict(self)
        path.write_text(json.dumps(d, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Calibration | None":
        try:
            d = json.loads(path.read_text())
            d["camera"] = tuple(d.get("camera", (325.0, 145.0, 930.0)))
            return cls(**d)
        except (OSError, ValueError, TypeError):
            return None

    # ------------------------------------------------------------ mapping
    def to_image(self, pts_mm: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts_mm, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self._h).reshape(-1, 2)

    def to_floor(self, pts_px: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts_px, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self._hinv).reshape(-1, 2)

    def raised(self, pts_mm: np.ndarray, h: float) -> np.ndarray:
        """Floor point on the same ray as points at height h above the floor."""
        cx, cy, hc = self.camera
        pts = np.asarray(pts_mm, dtype=np.float64).reshape(-1, 2)
        k = hc / max(hc - h, 1.0)
        return np.column_stack([cx + (pts[:, 0] - cx) * k, cy + (pts[:, 1] - cy) * k])

    def lowered(self, pts_floor: np.ndarray, h: float) -> np.ndarray:
        """Where a point seen at `pts_floor` stands, if it is h above the floor."""
        cx, cy, hc = self.camera
        pts = np.asarray(pts_floor, dtype=np.float64).reshape(-1, 2)
        k = max(hc - h, 1.0) / hc
        return np.column_stack([cx + (pts[:, 0] - cx) * k, cy + (pts[:, 1] - cy) * k])

    def image_of(self, pts_mm: np.ndarray, h: float = 0.0) -> np.ndarray:
        return self.to_image(self.raised(pts_mm, h) if h else pts_mm)

    @property
    def nadir(self) -> tuple[float, float]:
        return self.camera[0], self.camera[1]

    def rect_polygon(self, rect: list[float], h: float = 0.0) -> np.ndarray:
        x0, x1, y0, y1 = rect
        return self.image_of(np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]), h)

    def mm_per_px(self, x: float, y: float) -> float:
        a = self.to_image(np.array([[x, y], [x + 10, y]]))
        d = float(np.hypot(*(a[1] - a[0])))
        return 10.0 / d if d > 0 else 1.0
