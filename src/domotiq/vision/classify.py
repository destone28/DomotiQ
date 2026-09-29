# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What is in the photo taken at registration.

A YOLOX-Nano object detector (Apache-2.0, trained on the 80 classes of the
COCO dataset), run with onnxruntime on the board, looks at the photo from the
phone. The biggest confident detection gives the category proposed to the
visitor, who always confirms it: person, dog, cat, another animal, car, or
an object with a proposed name (chair, ball, suitcase...).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]

CATEGORY = {"person": "person", "dog": "dog", "cat": "cat", "car": "car", "truck": "car", "bus": "car"}
for _animal in ("bird", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "teddy bear"):
    CATEGORY[_animal] = "animal"

# names proposed for objects, in Italian (the English one is the COCO name)
NAMES_IT = {
    "bicycle": "bicicletta", "motorcycle": "moto", "airplane": "aereo", "train": "treno", "boat": "barca",
    "bench": "panchina", "backpack": "zaino", "umbrella": "ombrello", "handbag": "borsa", "suitcase": "valigia",
    "frisbee": "frisbee", "skis": "sci", "snowboard": "snowboard", "sports ball": "pallone", "kite": "aquilone",
    "skateboard": "skateboard", "surfboard": "tavola da surf", "tennis racket": "racchetta", "bottle": "bottiglia",
    "wine glass": "bicchiere", "cup": "tazza", "bowl": "ciotola", "banana": "banana", "apple": "mela",
    "orange": "arancia", "pizza": "pizza", "cake": "torta", "chair": "sedia", "couch": "divano",
    "potted plant": "pianta", "bed": "letto", "dining table": "tavolo", "toilet": "water", "tv": "televisore",
    "laptop": "computer", "cell phone": "telefono", "book": "libro", "clock": "orologio", "vase": "vaso",
    "teddy bear": "orsetto", "scissors": "forbici", "remote": "telecomando", "keyboard": "tastiera",
    "traffic light": "semaforo", "fire hydrant": "idrante", "stop sign": "cartello", "microwave": "microonde",
    "oven": "forno", "toaster": "tostapane", "sink": "lavandino", "refrigerator": "frigorifero",
}

SIZE = 416
STRIDES = (8, 16, 32)


def label_name(label: str | None, lang: str = "it") -> str | None:
    if not label:
        return None
    return NAMES_IT.get(label, label) if lang == "it" else label


class PhotoClassifier:
    def __init__(self, models_dir: Path) -> None:
        import onnxruntime as ort

        path = Path(models_dir) / "vision" / "yolox_nano.onnx"
        if not path.exists():
            raise FileNotFoundError(path)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        grids, strides = [], []
        for s in STRIDES:
            n = SIZE // s
            yv, xv = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
            grids.append(np.stack([xv, yv], axis=-1).reshape(-1, 2))
            strides.append(np.full((n * n, 1), s))
        self._grid = np.concatenate(grids).astype(np.float32)
        self._stride = np.concatenate(strides).astype(np.float32)

    def detect(self, img: np.ndarray, min_score: float = 0.3) -> list[tuple[str, float, list[float]]]:
        """(COCO label, score, [x0, y0, x1, y1]) of each object found, best first."""
        h, w = img.shape[:2]
        r = min(SIZE / h, SIZE / w)
        padded = np.full((SIZE, SIZE, 3), 114, np.uint8)
        resized = cv2.resize(img, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)
        padded[: resized.shape[0], : resized.shape[1]] = resized
        blob = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
        out = self.session.run(None, {self.input: blob})[0][0]
        xy = (out[:, :2] + self._grid) * self._stride
        wh = np.exp(out[:, 2:4]) * self._stride
        scores = out[:, 4:5] * out[:, 5:]
        cls = scores.argmax(axis=1)
        best = scores[np.arange(len(cls)), cls]
        keep = best >= min_score
        if not keep.any():
            return []
        xy, wh, cls, best = xy[keep], wh[keep], cls[keep], best[keep]
        boxes = np.concatenate([xy - wh / 2, xy + wh / 2], axis=1) / r
        idx = cv2.dnn.NMSBoxes([[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes],
                               best.tolist(), min_score, 0.45)
        idx = np.array(idx).reshape(-1)
        found = [(COCO[int(cls[i])], float(best[i]), [float(v) for v in boxes[i]]) for i in idx]
        return sorted(found, key=lambda f: -f[1])

    def classify(self, img: np.ndarray) -> tuple[str, str] | None:
        """(category, COCO label) of the main subject of the photo."""
        found = self.detect(img)
        if not found:
            return None
        h, w = img.shape[:2]

        def weight(f):
            x0, y0, x1, y1 = f[2]
            area = max(0.0, (min(x1, w) - max(x0, 0)) * (min(y1, h) - max(y0, 0))) / (w * h)
            return f[1] * np.sqrt(max(area, 1e-4))

        label = max(found, key=weight)[0]
        return CATEGORY.get(label, "object"), label

    def classify_file(self, path: str | Path) -> tuple[str, str] | None:
        img = cv2.imread(str(path))
        if img is None:
            return None
        try:
            return self.classify(img)
        except Exception:  # noqa: BLE001
            log.exception("photo classification")
            return None
