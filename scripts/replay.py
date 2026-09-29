# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Run the vision again on a sequence recorded by the staff.

A recording (Calibration → Record in the web app) is a folder under
var/recordings with the frames, the calibration, the empty-house reference
and what the house saw at the time. Replaying it on a PC shows what the
current code sees on the same frames, which is how the pipeline is tuned on
the real house without the house.

    .venv/bin/python scripts/replay.py var/recordings/rec-20261001-101500
    .venv/bin/python scripts/replay.py REC --video out.mp4      # frames with the tracks drawn
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402

from domotiq.layout import Layout  # noqa: E402
from domotiq.vision.engine import Engine  # noqa: E402
from domotiq.vision.geometry import Calibration  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("--video", help="write the frames with the tracks drawn to this .mp4")
    args = ap.parse_args()
    rec = Path(args.recording)
    calib = Calibration.load(rec / "calibration.json")
    ref = cv2.imread(str(rec / "reference.jpg"))
    if calib is None or ref is None:
        sys.exit("the recording has no calibration or reference")
    tmp = Path(tempfile.mkdtemp(prefix="domotiq-replay-"))
    engine = Engine(Layout.load(), tmp, tmp / "ds", tmp / "rec")
    ok = engine.set_corners([[u / calib.width, v / calib.height] for u, v in calib.corners])
    ok = ok["ok"] and engine.take_empty([ref] * 3)["ok"]
    if not ok:
        sys.exit("the calibration of the recording is not usable")
    recorded = {}
    log = rec / "detections.jsonl"
    if log.exists():
        for line in log.read_text().splitlines():
            d = json.loads(line)
            recorded[d["frame"]] = d
    frames = sorted(rec.glob("[0-9]*.jpg"))
    writer = None
    spent = []
    for path in frames:
        n = int(path.stem)
        img = cv2.imread(str(path))
        t_rec = recorded.get(n, {}).get("t", n * 0.1)
        t0 = time.perf_counter()
        tracks = engine.feed(img, t_rec)
        spent.append(time.perf_counter() - t0)
        then = recorded.get(n, {}).get("tracks", [])
        now = ", ".join(f"{t.identity or t.category}@{t.room}({t.x:.0f},{t.y:.0f}){'?' if t.uncertain else ''}"
                        f"{' in hand' if t.carried else ''}" for t in tracks)
        before = ", ".join(f"{t.get('identity') or t.get('category')}@{t.get('room')}" for t in then)
        print(f"{n:05d}  now: {now or '-'}")
        if before:
            print(f"       then: {before}")
        if args.video:
            out = engine.image(overlay=True)
            if writer is None:
                writer = cv2.VideoWriter(args.video, cv2.VideoWriter_fourcc(*"mp4v"), 10, out.shape[1::-1])
            writer.write(out)
    if writer is not None:
        writer.release()
    if spent:
        spent.sort()
        print(f"\n{len(spent)} frames, {1000 * spent[len(spent) // 2]:.0f} ms per frame (median)")


if __name__ == "__main__":
    main()
