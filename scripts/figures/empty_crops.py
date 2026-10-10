#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
""""niente" crops from the empty house: what a house looks like with nobody on it, under each light it has stored.

The network that knows the figurines learns "niente" from the blobs the house saw that were no figurine. A house it
has never seen (other furniture, other colours) has none of those yet, and the network finds figurines in its
furniture: an orange sofa taken for the yellow figurine. The empty houses of the calibration (var/calibration:
reference.png and empties/*.png) are a house with nobody on it by definition: square crops of the sizes of real
blobs, anywhere on the base, are all "niente".

    python scripts/figures/empty_crops.py <calibration dir> <out dir> [--per-picture N]

The calibration dir is var/calibration copied from the board. The out dir gets the crops and an index.json, to be
given to train.py with the other crops.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

from build_crops import crop    # in the same folder: the crops are made in the same way

SIDE_PX = (8, 70)      # sides of the blobs of figurines, lights and shadows seen by the house (640 x 480)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("calibration", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-picture", type=int, default=600)
    args = ap.parse_args()
    cal = json.loads((args.calibration / "calibration.json").read_text())
    base = np.array(cal["corners"], np.float32)
    pictures = [args.calibration / "reference.png"] + sorted((args.calibration / "empties").glob("*.png"))
    pictures = [p for p in pictures if p.exists()]
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(11)
    index = []
    for k, pic in enumerate(pictures):
        img = cv2.imread(str(pic))
        made = 0
        while made < args.per_picture:
            w, h = rng.randint(*SIDE_PX), rng.randint(*SIDE_PX)
            x = rng.uniform(base[:, 0].min(), base[:, 0].max() - w)
            y = rng.uniform(base[:, 1].min(), base[:, 1].max() - h)
            if cv2.pointPolygonTest(base, (x + w / 2, y + h / 2), False) < 0:
                continue                            # the middle of the blob on the base, as the house sees them
            bbox = [int(x), int(y), int(w), int(h)]
            name = f"empty-{pic.stem}-{made:04d}.png"
            cv2.imwrite(str(args.out / name), crop(img, bbox))
            # each picture its own block of time: train.py validates on blocks left out
            index.append({"file": name, "label": "niente", "rec": f"empty-{pic.stem}", "frame": made, "area": None,
                          "t": float(k * 100000 + made), "track": None, "bbox": bbox})
            made += 1
    (args.out / "index.json").write_text(json.dumps(index))
    print(f"{len(index)} crops of the empty house from {len(pictures)} pictures in {args.out}")


if __name__ == "__main__":
    main()
