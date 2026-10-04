# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The colour signature of a figurine.

Figurines are printed in a single colour, so what tells them apart from the
floor and from each other is their chroma: a histogram of a* and b* (the
colour axes of the Lab space, where lightness is kept apart and a shadow or
a dimmer light changes little), plus the median colour. Matching is a
Bhattacharyya distance on the histograms and a colour difference on the
medians.
"""

from __future__ import annotations

import cv2
import numpy as np

BINS = 12
RANGE = 64.0                  # a*, b* in [-64, 64] cover every printable colour
SIG_LEN = BINS * BINS + 3


def signature(lab_pixels: np.ndarray) -> np.ndarray:
    """lab_pixels: N x 3, L in 0..100, a* and b* centred on 0."""
    if len(lab_pixels) == 0:
        return np.zeros(SIG_LEN, np.float32)
    a = np.clip(lab_pixels[:, 1], -RANGE, RANGE - 1e-3)
    b = np.clip(lab_pixels[:, 2], -RANGE, RANGE - 1e-3)
    hist, _, _ = np.histogram2d(a, b, bins=BINS, range=[[-RANGE, RANGE], [-RANGE, RANGE]])
    # a little blur between neighbouring bins: a slight change of light must not jump a bin
    hist = cv2.GaussianBlur(hist.astype(np.float32), (5, 5), 1.0, borderType=cv2.BORDER_CONSTANT).ravel()
    hist /= max(float(hist.sum()), 1e-6)
    med = np.median(lab_pixels, axis=0).astype(np.float32)
    return np.concatenate([hist, med])


def distance(s1: np.ndarray, s2: np.ndarray) -> float:
    """0 = same colour, about 1 = unrelated."""
    s1, s2 = np.asarray(s1, np.float32), np.asarray(s2, np.float32)
    if len(s1) != SIG_LEN or len(s2) != SIG_LEN:
        return 1.0
    h1, h2 = s1[:-3], s2[:-3]
    bc = float(np.sum(np.sqrt(h1 * h2)))
    bhatta = float(np.sqrt(max(0.0, 1.0 - bc)))
    m1, m2 = s1[-3:], s2[-3:]
    # chroma matters most, lightness less (light and shadows change it), except for white,
    # grey and black figurines, which only lightness tells apart
    c = 0.5 * (float(np.hypot(m1[1], m1[2])) + float(np.hypot(m2[1], m2[2])))
    wl = 0.15 + 0.6 * (1.0 - min(c / 15.0, 1.0))
    de = float(np.sqrt(wl * (m1[0] - m2[0]) ** 2 + (m1[1] - m2[1]) ** 2 + (m1[2] - m2[2]) ** 2))
    return 0.55 * bhatta + 0.45 * min(de / 30.0, 1.0)


def distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """`distance` between every row of `a` and every row of `b` (signatures), in one go: a few dozen
    comparisons cost about as much as one."""
    a = np.asarray(a, np.float32).reshape(-1, SIG_LEN)
    b = np.asarray(b, np.float32).reshape(-1, SIG_LEN)
    bc = np.sqrt(np.maximum(a[:, :-3], 0.0)) @ np.sqrt(np.maximum(b[:, :-3], 0.0)).T
    bhatta = np.sqrt(np.maximum(0.0, 1.0 - bc))
    ma, mb = a[:, -3:], b[:, -3:]
    c = 0.5 * (np.hypot(ma[:, 1], ma[:, 2])[:, None] + np.hypot(mb[:, 1], mb[:, 2])[None, :])
    wl = 0.15 + 0.6 * (1.0 - np.minimum(c / 15.0, 1.0))
    d = ma[:, None, :] - mb[None, :, :]
    de = np.sqrt(wl * d[..., 0] ** 2 + d[..., 1] ** 2 + d[..., 2] ** 2)
    return 0.55 * bhatta + 0.45 * np.minimum(de / 30.0, 1.0)


def blend(old: np.ndarray, new: np.ndarray, weight: float = 0.1) -> np.ndarray:
    old, new = np.asarray(old, np.float32), np.asarray(new, np.float32)
    if len(old) != SIG_LEN:
        return new
    out = (1 - weight) * old + weight * new
    h = out[:-3]
    out[:-3] = h / max(float(h.sum()), 1e-6)
    return out


def chroma(sig: np.ndarray) -> float:
    s = np.asarray(sig, np.float32)
    return float(np.hypot(s[-2], s[-1])) if len(s) == SIG_LEN else 0.0


def to_hex(sig: np.ndarray) -> str:
    """The median colour as #rrggbb, for the web app."""
    s = np.asarray(sig, np.float32)
    if len(s) != SIG_LEN:
        return "#888888"
    lab = np.array([[[s[-3] * 255 / 100, s[-2] + 128, s[-1] + 128]]], dtype=np.uint8)
    b, g, r = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)[0, 0]
    return "#%02x%02x%02x" % (int(r), int(g), int(b))
