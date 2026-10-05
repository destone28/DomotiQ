# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The colour signature, counted directly: the same as with np.histogram2d."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from domotiq.vision.signature import BINS, RANGE, signature  # noqa: E402


def histogram2d_signature(lab_pixels):
    """The signature as it was counted before, with np.histogram2d."""
    a = np.clip(lab_pixels[:, 1], -RANGE, RANGE - 1e-3)
    b = np.clip(lab_pixels[:, 2], -RANGE, RANGE - 1e-3)
    hist, _, _ = np.histogram2d(a, b, bins=BINS, range=[[-RANGE, RANGE], [-RANGE, RANGE]])
    hist = cv2.GaussianBlur(hist.astype(np.float32), (5, 5), 1.0, borderType=cv2.BORDER_CONSTANT).ravel()
    hist /= max(float(hist.sum()), 1e-6)
    return np.concatenate([hist, np.median(lab_pixels, axis=0).astype(np.float32)])


def test_the_signature_counts_as_before():
    rng = np.random.default_rng(1)
    for n in (1, 25, 700, 3000):
        for px in (rng.normal(0, 35, (n, 3)),
                   rng.integers(-128, 128, (n, 3)),           # 8-bit Lab gives whole numbers: some on the bin edges
                   rng.choice([-64.0, -53.4, -32.0, 0.0, 10.66, 32.0, 63.999, 64.0], (n, 3))):
            px = px.astype(np.float32)
            assert np.array_equal(signature(px), histogram2d_signature(px))
