#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The vision of the house played again on recordings, against what the house told while recording them.

    python3 scripts/vision_bench.py var/recordings/rec-... [more] --identities var/config/identities.json
                                    [--figures models] [--consent]

Every recording (Calibration -> Record) holds the frames the house looked at and the presences it told then. They
are fed again to the vision of today (with the network that knows the figurines, if --figures gives the folder that
holds vision/figures.onnx; --consent: nothing new told before the network sees a figurine there). For every frame
the presences told now are compared with those told then, by place:
- "in più": told now, with nothing told then within NEAR_MM: a false presence, unless the house missed it then;
- "mancanti": told then with a name, nothing told now within NEAR_MM;
- "nomi diversi": in both, with another name.
A presence that was there at the start of the recording needs a few seconds to be found again (the start of the
house): the first START_S of every recording are not counted.

What the house told then is no truth: played again from nothing, the vision has not the names confirmed by hand,
the looks learned and the places of that time, so names differ between characters coloured alike even with no
network. The counts compare one version with another on the same frames; to see
what the network refused, --journal writes the journal of the vision (the crops) into a folder.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NEAR_MM = 35.0
START_S = 8.0


def bench(rec: Path, identities: list, figures: Path | None, consent: bool, journal: Path | None = None) -> dict:
    import cv2

    from domotiq.layout import Layout
    from domotiq.vision.engine import Engine
    lines = [json.loads(line) for line in open(rec / "detections.jsonl")]
    tmp = Path(tempfile.mkdtemp())
    (tmp / "c").mkdir()
    shutil.copy(rec / "calibration.json", tmp / "c" / "calibration.json")
    cv2.imwrite(str(tmp / "c" / "reference.png"), cv2.imread(str(rec / "reference.jpg")))
    e = Engine(Layout.load(), tmp / "c", tmp / "ds", tmp / "rc")
    e.set_identities(identities)
    if figures is not None:
        from domotiq.vision.figures import FigureClassifier
        e.figures = FigureClassifier(figures)
        e.figures_consent = consent
    if journal is not None:
        e.journal_dir = journal / rec.name
        e.journal_dir.mkdir(parents=True, exist_ok=True)
    names = {i.id: i.name for i in identities}
    extra, missing, renamed, counted = Counter(), Counter(), Counter(), 0
    extra_frames = 0
    t_first = lines[0]["t"] if lines else 0.0
    spent = 0.0
    for d in lines:
        f = rec / f"{d['frame']:05d}.jpg"
        img = cv2.imread(str(f)) if f.exists() else None
        if img is None:
            continue
        t0 = time.perf_counter()
        now = e.feed(img, d["t"])
        spent += time.perf_counter() - t0
        if d["t"] - t_first < START_S:
            continue
        counted += 1
        then = [(t["x"], t["y"], names.get(t.get("identity") or "", "?")) for t in d["tracks"] if not t.get("carried")]
        told = [(t.x, t.y, names.get(t.identity or "", "?")) for t in now if not t.carried]
        any_extra = False
        for x, y, name in told:
            near = [n for (a, b, n) in then if np.hypot(a - x, b - y) < NEAR_MM]
            if not near:
                extra[name] += 1
                any_extra = True
            elif name not in near:
                renamed[(near[0], name)] += 1
        for a, b, name in then:
            if name != "?" and not any(np.hypot(a - x, b - y) < NEAR_MM for x, y, _ in told):
                missing[name] += 1
        extra_frames += any_extra
    st = e.status()
    shutil.rmtree(tmp, ignore_errors=True)
    return {"frames": counted, "extra_frames": extra_frames, "extra": dict(extra), "missing": dict(missing),
            "renamed": {f"{a} -> {b}": n for (a, b), n in renamed.items()}, "figures": st.get("figures"),
            "ms_per_frame": round(1000 * spent / max(len(lines), 1), 1)}


def main() -> None:
    from domotiq.model import Identity
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("recordings", nargs="+", type=Path)
    ap.add_argument("--identities", type=Path, required=True)
    ap.add_argument("--figures", type=Path, default=None, help="the folder with vision/figures.onnx")
    ap.add_argument("--consent", action="store_true")
    ap.add_argument("--journal", type=Path, default=None, help="write the journal of the vision (crops) here")
    args = ap.parse_args()
    raw = json.loads(args.identities.read_text())
    items = raw if isinstance(raw, list) else raw.get("identities", raw)
    items = list(items.values()) if isinstance(items, dict) else items
    identities = [Identity.from_dict(i) for i in items]
    for rec in args.recordings:
        r = bench(rec, identities, args.figures, args.consent, args.journal)
        print(f"{rec.name}: {r['frames']} frames counted, {r['ms_per_frame']} ms a frame")
        print(f"  frames with a presence in più: {r['extra_frames']} ({100 * r['extra_frames'] / max(r['frames'], 1):.1f}%)"
              f" | in più (frames x presence): {r['extra']}")
        print(f"  mancanti: {r['missing']}")
        print(f"  nomi diversi: {r['renamed']}")
        print(f"  network: {r['figures']}")


if __name__ == "__main__":
    main()
