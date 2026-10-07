#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Labelled crops of the figurines from the recordings of the house (Calibration -> Record).

Every frame of a recording has the blobs the house saw (bbox in pixels, middle in mm) and the tracks it followed
(with the character's identity and, since 7 October, the bbox of the blob the track was matched to). The blob of a
named track is a crop of that character; a blob that is no track's, no hand, of a figurine's size, in a frame where
the house was following characters, is "niente" (light, shadow, a module). Recordings without the bbox of the
tracks are left out: matched by the place on the map, which is fixed and seen from above, their labels were wrong
(a piece of furniture taken for Mister Brown, Viola taken for "niente"). Figurines in the bathroom are blurred in the
recordings and are left out too. Crops are square around the blob, with a margin, resized to SIZE.

    python scripts/figures/build_crops.py <recordings dir> <identities.json> <out dir> [--journal <journal dir>]

The recordings and identities.json are copied from the board (var/recordings/rec-*, var/config/identities.json).
With --journal (var/journal copied from the board), the crops people confirmed or corrected in the web app (Vision
journal) are added with the label they gave: they count more than the house's own labels.

With --fixes, the corrections made on the plan of the web app are applied to the whole time a track stood where it
was corrected: {"track id": [label, from, to]}, "niente" for a presence dismissed, the name for a presence named
(also while the house had another name for it, or none). scripts/figures/web_fixes.py finds them in the database of
the house (var/domotiq.db).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

SIZE = 64
MARGIN = 0.35          # around the blob, share of its longer side
MATCH_MM = 20.0        # blob middle to track middle
FAR_MM = 45.0          # "niente": at least this far from every track
MIN_MM2, MAX_MM2 = 150.0, 6000.0
EVERY = 2              # a still figurine looks the same frame after frame: one crop every few frames per track
SOON_S, SOON_MM = 10.0, 35.0   # a blob where a track is within this long before or after was a figurine (just put
                               # down, not yet told to the house), not "niente"


def crop(img: np.ndarray, bbox: list[int]) -> np.ndarray:
    x, y, w, h = bbox
    side = max(w, h) * (1 + 2 * MARGIN)
    cx, cy = x + w / 2, y + h / 2
    x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
    x1, y1 = int(round(cx + side / 2)), int(round(cy + side / 2))
    H, W = img.shape[:2]
    pad = max(0, -x0, -y0, x1 - W, y1 - H)
    if pad:
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 + pad, y1 + pad
    return cv2.resize(img[y0:y1, x0:x1], (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def fixed(fix, t: float) -> str | None:
    """The label a correction gives at time t: [label, from, to], or a list of them (what it was while a figurine
    stood there, "niente" once it was taken away and the house kept it, "drop" while it is not clear)."""
    if not fix:
        return None
    for label, a, b in ([fix] if isinstance(fix[0], str) else fix):
        if a <= t <= b:
            return label
    return None


def journal_crops(journal: Path, out: Path, index: list, counts: Counter) -> None:
    """The crops of the journal of the vision that somebody labelled in the web app."""
    labels = json.loads((journal / "labels.json").read_text(encoding="utf-8")) if (journal / "labels.json").exists() else {}
    for k, (entry_id, lab) in enumerate(sorted(labels.items())):
        src = journal / f"{entry_id}.jpg"
        img = cv2.imread(str(src)) if src.exists() else None
        if img is None:
            continue
        name = f"journal_{entry_id}.png"
        cv2.imwrite(str(out / name), cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_AREA))
        index.append({"file": name, "label": lab["label"], "rec": "journal", "frame": k, "area": None, "t": None})
        counts[lab["label"]] += 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("recordings", type=Path)
    ap.add_argument("identities", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--journal", type=Path, default=None)
    ap.add_argument("--fixes", type=Path, default=None, help="corrections made on the plan (web_fixes.py)")
    args = ap.parse_args()
    fixes = json.loads(args.fixes.read_text()) if args.fixes else {}
    recs, ids_file, out = args.recordings, args.identities, args.out
    raw = json.loads(ids_file.read_text())
    items = raw if isinstance(raw, list) else raw.get("identities", raw)
    items = list(items.values()) if isinstance(items, dict) else items
    names = {i["id"]: i["name"] for i in items}
    out.mkdir(parents=True, exist_ok=True)
    index, counts = [], Counter()
    for rec in sorted(recs.glob("rec-*")):
        log = rec / "detections.jsonl"
        if not log.exists():
            continue
        last: dict[str, int] = {}
        lines = [json.loads(line) for line in open(log)]
        if not any("bbox" in t for d in lines for t in d.get("tracks", [])):
            print(f"{rec.name}: no bbox of the tracks, left out")
            continue
        # where tracks were, frame by frame, to tell a figurine not yet followed from "niente"
        times = np.array([d.get("t", 0.0) for d in lines])
        where = [np.array([[t["x"], t["y"]] for t in d.get("tracks", [])] or np.zeros((0, 2))) for d in lines]

        def tracked_near(t0: float, x: float, y: float) -> bool:
            lo, hi = np.searchsorted(times, t0 - SOON_S), np.searchsorted(times, t0 + SOON_S)
            return any(len(w) and float(np.min(np.hypot(w[:, 0] - x, w[:, 1] - y))) < SOON_MM for w in where[lo:hi])
        for d in lines:
            tracks = [t for t in d.get("tracks", []) if not t.get("carried")]
            obs = [o for o in d.get("observations", []) if not o.get("hand")]
            if not tracks:
                continue
            wanted = []
            boxes = [t["bbox"] for t in tracks if t.get("bbox")]
            for t in tracks:
                fix = fixed(fixes.get(t["id"]), d.get("t", 0.0))
                if fix is not None:
                    # somebody said on the plan what this was: it counts more than what the house said
                    if t.get("bbox") and t.get("room") != "bathroom" and not t.get("hidden") and fix != "drop":
                        wanted.append((fix, t["id"], t["bbox"], None))
                    continue
                if t.get("bbox") and t.get("identity") in names and not t.get("uncertain") \
                        and t.get("room") != "bathroom" and not t.get("hidden"):
                    wanted.append((names[t["identity"]], t["id"], t["bbox"], None))
            # "niente" only where every track has its blob in this frame: a track not seen now may be that blob
            for o in (obs if len(boxes) == len(tracks) else []):
                if not MIN_MM2 <= o.get("area", 0) <= MAX_MM2:
                    continue
                x, y, w, h = o["bbox"]
                if any(x < bx + bw + 4 and bx - 4 < x + w and y < by + bh + 4 and by - 4 < y + h
                       for bx, by, bw, bh in boxes):
                    continue                     # touching the blob of a track: a piece of it
                ox, oy = o["centroid"]
                if min(float(np.hypot(ox - t["x"], oy - t["y"])) for t in tracks) < FAR_MM:
                    continue
                if tracked_near(d.get("t", 0.0), ox, oy):
                    continue                     # a figurine before or after the house followed it
                wanted.append(("niente", f"n{round(ox / 20)}-{round(oy / 20)}", o["bbox"], o.get("area")))
            img = None
            for label, key, bbox, area in wanted:
                if d["frame"] - last.get(key, -99) < EVERY:
                    continue
                last[key] = d["frame"]
                if img is None:
                    f = rec / f"{d['frame']:05d}.jpg"
                    img = cv2.imread(str(f)) if f.exists() else None
                    if img is None:
                        break
                name = f"{rec.name}_{d['frame']:05d}_{len(index):06d}.png"
                cv2.imwrite(str(out / name), crop(img, bbox))
                index.append({"file": name, "label": label, "rec": rec.name, "frame": d["frame"],
                              "area": area, "t": d.get("t"), "track": key if key.startswith("t-") else None,
                              "bbox": list(bbox)})
                counts[label] += 1
    if args.journal is not None:
        journal_crops(args.journal, out, index, counts)
    (out / "index.json").write_text(json.dumps(index))
    print(f"{len(index)} crops:", dict(counts.most_common()))


if __name__ == "__main__":
    main()
