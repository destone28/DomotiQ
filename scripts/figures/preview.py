#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""A sheet with some crops of every class, to check the labels by eye.

    python preview.py <crops dir> <sheet.png>
"""
import json
import sys

import cv2
import numpy as np

d = sys.argv[1]
idx = json.load(open(d + "/index.json"))
by = {}
for e in idx:
    by.setdefault(e["label"], []).append(e["file"])
rows = []
for label, files in sorted(by.items()):
    sel = files[:: max(1, len(files) // 12)][:12]
    tiles = [cv2.imread(d + "/" + f) for f in sel]
    while len(tiles) < 12:
        tiles.append(np.zeros((64, 64, 3), np.uint8))
    row = np.hstack(tiles)
    cv2.rectangle(row, (0, 0), (8 * len(label) + 4, 14), (0, 0, 0), -1)
    cv2.putText(row, label, (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    rows.append(row)
cv2.imwrite(sys.argv[2], cv2.resize(np.vstack(rows), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
print({k: len(v) for k, v in by.items()})
