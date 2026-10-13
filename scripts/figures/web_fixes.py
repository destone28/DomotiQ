#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The corrections made on the plan of the web app, as labels for the crops of the figurines.

A presence dismissed ("there is nothing there") was "niente" all the time it stood there; a presence named was that
character all the time it stood there, also while the house had another name for it, or none. They are found in the
database of the house (var/domotiq.db, copied from the board): the commands of the web app, and the positions of
every track (once a second) to know which track it was and for how long it stood in that place.

    python scripts/figures/web_fixes.py <domotiq.db> <identities.json> <out fixes.json> [--since "YYYY-MM-DD HH:MM"]

The result goes to build_crops.py --fixes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

STILL_MM = 30.0        # the place of a track: where it stood within this distance


def still(h: list, k: int) -> tuple[float, float]:
    """The stretch of a track's positions around sample k where it stood within STILL_MM of where it was then."""
    x, y = h[k][2], h[k][3]
    a = b = k
    while a > 0 and abs(h[a - 1][2] - x) + abs(h[a - 1][3] - y) < STILL_MM:
        a -= 1
    while b < len(h) - 1 and abs(h[b + 1][2] - x) + abs(h[b + 1][3] - y) < STILL_MM:
        b += 1
    return h[a][0] - 1.0, h[b][0] + 1.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("db", type=Path)
    ap.add_argument("identities", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--since", default=None, help="local time, YYYY-MM-DD HH:MM")
    args = ap.parse_args()
    raw = json.loads(args.identities.read_text())
    items = raw if isinstance(raw, list) else raw.get("identities", raw)
    items = list(items.values()) if isinstance(items, dict) else items
    names = {i["id"]: i["name"] for i in items}
    since = time.mktime(time.strptime(args.since, "%Y-%m-%d %H:%M")) if args.since else 0.0
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    pos: dict[str, list] = defaultdict(list)
    for row in db.execute("SELECT ts, track, identity, x, y, room FROM positions WHERE ts >= ? ORDER BY ts",
                          (since - 3600,)):
        pos[row[1]].append((row[0], row[2], row[3], row[4], row[5]))
    fixes, missed = {}, 0
    for ts, data in db.execute("SELECT ts, data FROM events WHERE type = 'command' AND ts >= ? ORDER BY ts", (since,)):
        c = json.loads(data)
        body = c.get("body") or {}
        if c.get("name") not in ("dismiss", "identity"):
            continue
        tid, k = body.get("track"), None
        if tid in pos:                          # the command recorded its track: that one
            h = pos[tid]
            k = min(range(len(h)), key=lambda i: abs(h[i][0] - ts))
        elif c["name"] == "dismiss":
            # the track that was last seen in that room just before, with that name (or none)
            cand = [(ts - h[-1][0], t) for t, h in pos.items() if ts - 60 <= h[-1][0] <= ts + 1
                    and h[-1][4] == body.get("room")
                    and (not body.get("name") or names.get(h[-1][1] or "") in (body["name"], None))]
            if cand:
                tid = min(cand)[1]
                k = len(pos[tid]) - 1
        else:
            # the track that took that name right then (or had it right after)
            want = {i for i, n in names.items() if n == body.get("name")}
            cand = [(abs(h[i][0] - ts), t, i) for t, h in pos.items() for i in range(1, len(h))
                    if ts - 1 <= h[i][0] <= ts + 3 and h[i][1] in want and h[i - 1][1] not in want]
            cand = cand or [(abs(h[i][0] - ts) + 10, t, i) for t, h in pos.items() for i in range(len(h))
                            if ts - 1 <= h[i][0] <= ts + 6 and h[i][1] in want]
            if cand:
                _, tid, k = min(cand)
        if k is None:
            missed += 1
            continue
        a, b = still(pos[tid], k)
        fixes[tid] = ["niente" if c["name"] == "dismiss" else body["name"], a, b]
    args.out.write_text(json.dumps(fixes, indent=0, ensure_ascii=False))
    print(f"{len(fixes)} tracks corrected, {missed} corrections not found again on the tracks")


if __name__ == "__main__":
    main()
