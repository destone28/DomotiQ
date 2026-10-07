# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The corrections made on the plan of the web app become labels for the network of the figurines
(scripts/figures/web_fixes.py, build_crops.py --fixes)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "scripts" / "figures"


def _db(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE positions (ts REAL, track TEXT, identity TEXT, x REAL, y REAL, room TEXT)")
    db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts REAL, type TEXT, level TEXT, data TEXT)")
    for k in range(20):
        # a phantom in the kitchen, dismissed at 1020 (recorded with its track since 7 October)
        db.execute("INSERT INTO positions VALUES (?,?,?,?,?,?)", (1000.0 + k, "t-ghost", None, 100.0, 100.0, "kitchen"))
        # pink lying on the bed, called Rossana by the house until it was named Rossellina at 1010 (no track
        # recorded: an older event), then carried to the living room at 1015
        place = (300.0, 50.0, "bedroom") if k < 15 else (500.0, 200.0, "living")
        ident = "id-rossana" if k < 10 else "id-rossellina"
        db.execute("INSERT INTO positions VALUES (?,?,?,?,?,?)", (1000.0 + k, "t-pink", ident) + place)
    db.execute("INSERT INTO events (ts, type, level, data) VALUES (?,?,?,?)", (1020.5, "command", "info", json.dumps(
        {"name": "dismiss", "body": {"name": "", "room": "kitchen", "track": "t-ghost"}})))
    db.execute("INSERT INTO events (ts, type, level, data) VALUES (?,?,?,?)", (1009.6, "command", "info", json.dumps(
        {"name": "identity", "body": {"name": "Rossellina"}})))
    db.commit()
    db.close()


def test_the_corrections_on_the_plan_become_labels(tmp_path):
    _db(tmp_path / "domotiq.db")
    ids = [{"id": "id-rossana", "name": "Rossana"}, {"id": "id-rossellina", "name": "Rossellina"}]
    (tmp_path / "identities.json").write_text(json.dumps(ids))
    subprocess.run([sys.executable, str(FIGURES / "web_fixes.py"), str(tmp_path / "domotiq.db"),
                    str(tmp_path / "identities.json"), str(tmp_path / "fixes.json")], check=True, capture_output=True)
    fixes = json.loads((tmp_path / "fixes.json").read_text())
    assert fixes["t-ghost"][0] == "niente" and fixes["t-ghost"][1] <= 1000.0 and fixes["t-ghost"][2] >= 1019.0
    # the name counts while it stood on the bed, also when the house called it Rossana; not after the hand moved it
    label, start, end = fixes["t-pink"]
    assert label == "Rossellina" and start <= 1000.0 and 1014.0 <= end < 1015.5

    # a recording with both tracks: their crops take the labels of the corrections
    rec = tmp_path / "recs" / "rec-20261007-000000"
    rec.mkdir(parents=True)
    img = np.full((480, 640, 3), 90, np.uint8)
    cv2.rectangle(img, (100, 100), (120, 130), (180, 120, 230), -1)
    lines = []
    for k, t in enumerate((1005.0, 1012.0, 1017.0)):
        cv2.imwrite(str(rec / f"{k + 1:05d}.jpg"), img)
        lines.append({"t": t, "frame": k + 1, "observations": [], "tracks": [
            {"id": "t-ghost", "identity": None, "x": 100.0, "y": 100.0, "room": "kitchen", "bbox": [300, 300, 20, 30]},
            {"id": "t-pink", "identity": "id-rossana" if t < 1010 else "id-rossellina", "x": 300.0, "y": 50.0,
             "room": "bedroom", "bbox": [100, 100, 20, 30]}]})
    (rec / "detections.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    subprocess.run([sys.executable, str(FIGURES / "build_crops.py"), str(tmp_path / "recs"),
                    str(tmp_path / "identities.json"), str(tmp_path / "crops"), "--fixes", str(tmp_path / "fixes.json")],
                   check=True, capture_output=True)
    index = json.loads((tmp_path / "crops" / "index.json").read_text())
    got = {(e["frame"], e["track"]): e["label"] for e in index}
    assert got[(1, "t-ghost")] == "niente" and got[(1, "t-pink")] == "Rossellina"   # the house said Rossana there
    assert got[(3, "t-pink")] == "Rossellina"            # after the correction: the house's own name, the same
