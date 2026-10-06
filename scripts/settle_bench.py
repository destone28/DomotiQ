#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""How many frames settle the place of a figurine on the map, measured on recordings of the webcam.

    python3 scripts/settle_bench.py var/recordings/rec-... [more recordings] [--identities var/config/identities.json]

Every recording (made from Calibration -> Record) is played through the vision of the house; for every followed
figurine it keeps, frame by frame, where its blob is (before any smoothing) and whether a hand is close to it
(vision/tracker.py, HAND_NEAR_MM). A "still time" starts HAND_NEAR_S after a hand left it (or when it is first
seen) and lasts until the next hand, at least MIN_S: its place is the median of all of it. The table tells how far
from that place the median of the first N frames is: SETTLE_FRAMES is the smallest N that is always close.
Only the frames the vision looked at count (at rest it looks at one a second).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MIN_S = 3.0
NS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30]


def series(rec: Path, identities: Path | None) -> dict[str, list]:
    """track -> [(time, x, y, hand close)], x and y None when not seen in that frame."""
    import cv2

    from domotiq.layout import Layout
    from domotiq.model import Identity
    from domotiq.vision.engine import Engine
    times = {}
    for line in open(rec / "detections.jsonl"):
        d = json.loads(line)
        times[d["frame"]] = d["t"]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "c").mkdir()
    shutil.copy(rec / "calibration.json", tmp / "c" / "calibration.json")
    cv2.imwrite(str(tmp / "c" / "reference.png"), cv2.imread(str(rec / "reference.jpg")))
    e = Engine(Layout.load(), tmp / "c", tmp / "ds", tmp / "rc")
    if identities is not None:
        raw = json.loads(identities.read_text())
        items = raw if isinstance(raw, list) else raw.get("identities", raw)
        items = list(items.values()) if isinstance(items, dict) else items
        e.set_identities([Identity.from_dict(i) for i in items])
    out: dict[str, list] = defaultdict(list)
    for n in sorted(times):
        f = rec / f"{n:05d}.jpg"
        if not f.exists():
            continue
        t, looked = times[n], e.looked
        e.feed(cv2.imread(str(f)), t)
        tr = e.tracker
        if tr is None or e.looked == looked:
            continue                          # resting: the frame was not looked at
        for vt in tr.tracks.values():
            near = vt.hand_at == t
            if vt.obs is None or vt.carried or vt.frame != tr.frame:
                out[vt.id].append((t, None, None, near))
            else:
                out[vt.id].append((t, *vt.obs.position(tr.calib, vt.category, tr.tops), near))
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def main() -> None:
    from domotiq.vision.tracker import HAND_NEAR_S, SETTLE_FRAMES
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("recordings", nargs="+", type=Path)
    ap.add_argument("--identities", type=Path, default=None)
    args = ap.parse_args()
    errs: dict[int, list[float]] = {n: [] for n in NS}
    periods = 0
    for rec in args.recordings:
        for pts in series(rec, args.identities).values():
            last_hand, cur = float("-inf"), []
            for t, x, y, near in pts + [(float("inf"), None, None, True)]:
                if near:
                    seen = [(s, a, b) for s, a, b in cur if a is not None]
                    if len(seen) >= 2 and seen[-1][0] - seen[0][0] >= MIN_S:
                        periods += 1
                        xs, ys = np.array([p[1] for p in seen]), np.array([p[2] for p in seen])
                        ref = np.array([np.median(xs), np.median(ys)])
                        for n in NS:
                            if len(seen) >= n:
                                est = np.array([np.median(xs[:n]), np.median(ys[:n])])
                                errs[n].append(float(np.hypot(*(est - ref))))
                    cur, last_hand = [], t
                elif t - last_hand > HAND_NEAR_S:
                    cur.append((t, x, y))
    print(f"still times: {periods} (SETTLE_FRAMES is {SETTLE_FRAMES})")
    print("  N  times   distance from the place it keeps, mm: median   p90    p95    max")
    for n in NS:
        e = np.array(errs[n])
        if len(e):
            print(f"{n:3d} {len(e):6d}{'':40s}{np.median(e):6.2f} {np.percentile(e, 90):6.2f} "
                  f"{np.percentile(e, 95):6.2f} {e.max():6.1f}")


if __name__ == "__main__":
    main()
