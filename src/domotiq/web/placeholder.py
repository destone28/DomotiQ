# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The live view when there is no camera frame.

In simulation it draws the house seen from above with the virtual
figurines, so the "live" page is useful on a PC too; otherwise it shows
a card saying the webcam is not connected.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from ..app import Context

_cache: dict[str, object] = {"key": None, "jpg": b"", "at": 0.0}


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 128, 128, 128
    return b, g, r


def render(ctx: "Context", width: int = 640) -> bytes:
    now = time.time()
    sim = ctx.sim
    key = (sim.enabled, sim.changed_at, tuple((t.id, round(t.x), round(t.y)) for t in ctx.house.tracks.values()),
           tuple(sorted((k, v["color"], v["effect"]) for k, v in ctx.lights.state().items())))
    if _cache["key"] == key and now - float(_cache["at"]) < 2.0:
        return _cache["jpg"]  # type: ignore[return-value]
    img = draw_plan(ctx, width) if sim.enabled else _card(width, "Webcam non collegata  ·  No webcam")
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    jpg = buf.tobytes() if ok else b""
    _cache.update(key=key, jpg=jpg, at=now)
    return jpg


def _card(width: int, text: str) -> np.ndarray:
    h = int(width * 0.75)
    img = np.full((h, width, 3), (60, 58, 54), np.uint8)
    cv2.putText(img, text, (24, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (230, 230, 230), 2, cv2.LINE_AA)
    return img


def draw_plan(ctx: "Context", width: int = 640) -> np.ndarray:
    lay = ctx.layout
    x0, x1, y0, y1 = lay.view.x0, lay.view.x1, lay.view.y0, lay.view.y1
    scale = width / (x1 - x0)
    h = int((y1 - y0) * scale)
    img = np.full((h, width, 3), (70, 74, 78), np.uint8)

    def pt(x: float, y: float) -> tuple[int, int]:
        # the camera sees the back of the house at the top of the image
        return int((x - x0) * scale), int((y1 - y) * scale)

    def rect(r, color, thick=-1):
        cv2.rectangle(img, pt(r[0], r[3]), pt(r[1], r[2]), color, thick)

    raw = lay.raw
    rect(raw["base"], (196, 198, 200))
    for lawn in raw.get("lawns", []):
        rect(lawn, (80, 150, 95))
    rect(raw["path"], (185, 187, 190))
    for f in raw["furniture"]:
        color = _hex(f.get("color", "#999999"))
        if "circle" in f:
            cx, cy, r = f["circle"]
            cv2.circle(img, pt(cx, cy), int(r * scale), color, -1)
        else:
            rect(f["rect"], color)
    lights = ctx.lights.state()
    for li in raw["lights"]:
        st = lights.get(li["id"], {})
        if st.get("effect", "off") != "off":
            cx = (li["rect"][0] + li["rect"][1]) / 2
            cy = (li["rect"][2] + li["rect"][3]) / 2
            overlay = img.copy()
            cv2.circle(overlay, pt(cx, cy), int(45 * scale), _hex(st.get("color", "#ffffff")), -1)
            img = cv2.addWeighted(overlay, 0.35, img, 0.65, 0)
    for w in raw["walls"]:
        rect(w["rect"], (245, 245, 245) if w.get("kind") != "fence" else (90, 120, 150))
    for d in raw["doors"]:
        rect(d["rect"], (196, 198, 200))
    for t in ctx.house.tracks.values():
        r = 14 if t.category == "person" else 10 if t.category in ("dog", "cat", "animal") else 12
        if t.category == "car":
            cv2.rectangle(img, pt(t.x - 45, t.y + 20), pt(t.x + 45, t.y - 20), _hex(t.color), -1)
        else:
            cv2.circle(img, pt(t.x, t.y), int(r * scale * 1.6), _hex(t.color), -1)
            cv2.circle(img, pt(t.x, t.y), int(r * scale * 1.6), (30, 30, 30), 1)
    bath = lay.rooms.get("bathroom")
    if bath:
        (ax, ay), (bx, by) = pt(bath.rect.x0 - 10, bath.rect.y1 + 10), pt(bath.rect.x1 + 10, bath.rect.y0 - 10)
        ax, bx = max(ax, 0), min(bx, width)
        ay, by = max(ay, 0), min(by, h)
        if bx > ax and by > ay:
            roi = img[ay:by, ax:bx]
            img[ay:by, ax:bx] = cv2.GaussianBlur(roi, (0, 0), 9)
    cv2.putText(img, "SIMULAZIONE - SIMULATION", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    return img
