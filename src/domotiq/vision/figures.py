# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""A second opinion on a blob: one of the characters of the house, or "niente" (a light, a shadow, a module).

A small convolutional network, trained on crops of the figurines seen by the webcam of the house under different
lights and shadows (scripts/figures/), run with onnxruntime. The crop is the one the network learned from: a square
around the blob with a margin, at the size it was trained on.

models/vision/figures.onnx holds the network, figures.json its classes and how its crops are made. Without them the
house works as before.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

NOTHING = "niente"


def square_crop(img: np.ndarray, bbox, margin: float, size: int) -> np.ndarray:
    """A square around the blob (x, y, w, h), with `margin` of its longer side on every side, at `size` pixels."""
    x, y, w, h = (float(v) for v in bbox)
    side = max(w, h) * (1 + 2 * margin)
    cx, cy = x + w / 2, y + h / 2
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    x1, y1 = int(round(cx + side / 2)), int(round(cy + side / 2))
    H, W = img.shape[:2]
    pad = max(0, -x0, -y0, x1 - W, y1 - H)
    if pad:
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 + pad, y1 + pad
    return cv2.resize(img[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_AREA)


class FigureClassifier:
    def __init__(self, models_dir: Path, threads: int = 1) -> None:
        import onnxruntime as ort

        folder = Path(models_dir) / "vision"
        meta = json.loads((folder / "figures.json").read_text(encoding="utf-8"))
        self.classes: list[str] = list(meta["classes"])
        self.size = int(meta.get("size", 64))
        self.margin = float(meta.get("margin", 0.35))
        self.mean, self.std = float(meta.get("mean", 0.5)), float(meta.get("std", 0.25))
        self.rgb = bool(meta.get("rgb", True))
        self.not_p = float(meta["not_p"]) if meta.get("not_p") else None   # measured with this network when trained
        # the characters it mixes up even when sure, measured when trained: it does not choose between them
        self.confused = [tuple(pair) for pair in meta.get("confused", []) if len(pair) == 2]
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads      # the rest of the vision runs on the other cores
        self.session = ort.InferenceSession(str(folder / "figures.onnx"), opts, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        log.info("figure classifier: %d classes (%s)", len(self.classes), ", ".join(self.classes))

    def classify(self, img: np.ndarray, bboxes: list) -> list[tuple[str, float]]:
        """(class, probability) of each blob, in one pass."""
        if not bboxes:
            return []
        crops = np.stack([square_crop(img, b, self.margin, self.size) for b in bboxes]).astype(np.float32)
        if self.rgb:
            crops = crops[..., ::-1]
        x = ((crops / 255.0 - self.mean) / self.std).transpose(0, 3, 1, 2)
        logits = self.session.run(None, {self.input: np.ascontiguousarray(x)})[0]
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        p = e / e.sum(axis=1, keepdims=True)
        best = p.argmax(axis=1)
        return [(self.classes[int(i)], float(p[k, int(i)])) for k, i in enumerate(best)]
