# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house remembers: events, positions, the change log and the bin.

SQLite in WAL mode, one connection guarded by a lock: the traffic is a few
writes per second at most, and a pull of the power plug must never leave the
database unreadable.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS positions (
    ts REAL NOT NULL,
    track TEXT NOT NULL,
    identity TEXT,
    x REAL NOT NULL,
    y REAL NOT NULL,
    room TEXT
);
CREATE INDEX IF NOT EXISTS positions_ts ON positions(ts);
CREATE INDEX IF NOT EXISTS positions_identity ON positions(identity, ts);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    device TEXT,
    nickname TEXT,
    entity TEXT NOT NULL,
    entity_id TEXT,
    action TEXT NOT NULL,
    before TEXT,
    after TEXT
);

CREATE TABLE IF NOT EXISTS trash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    data TEXT NOT NULL,
    device TEXT,
    nickname TEXT
);
"""

EVENT_RETENTION_S = 7 * 24 * 3600
POSITION_RETENTION_S = 24 * 3600
TRASH_RETENTION_S = 24 * 3600


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, args)

    def _query(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    # ------------------------------------------------------------ events
    def add_event(self, type_: str, data: dict[str, Any], level: str = "info",
                  ts: float | None = None) -> int:
        cur = self._exec("INSERT INTO events(ts, type, level, data) VALUES (?,?,?,?)",
                         (ts or time.time(), type_, level, json.dumps(data, ensure_ascii=False)))
        return int(cur.lastrowid)

    def events(self, limit: int = 200, before: float | None = None,
               types: list[str] | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM events"
        where, args = [], []
        if before:
            where.append("ts < ?")
            args.append(before)
        if types:
            where.append("type IN (%s)" % ",".join("?" * len(types)))
            args.extend(types)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        rows = self._query(sql, tuple(args))
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    # ------------------------------------------------------------ positions
    def add_positions(self, rows: list[tuple]) -> None:
        """rows: (ts, track, identity, x, y, room)"""
        if not rows:
            return
        with self._lock:
            self._db.executemany("INSERT INTO positions VALUES (?,?,?,?,?,?)", rows)

    def history(self, identity: str, since: float) -> list[dict[str, Any]]:
        return self._query("SELECT ts, x, y, room FROM positions WHERE identity=? AND ts>=? "
                           "ORDER BY ts", (identity, since))

    def room_changes(self, identity: str, since: float) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        last = None
        for r in self.history(identity, since):
            if r["room"] != last:
                out.append({"ts": r["ts"], "room": r["room"]})
                last = r["room"]
        return out

    # ------------------------------------------------------------ audit log
    def add_audit(self, entity: str, entity_id: str | None, action: str,
                  before: Any = None, after: Any = None,
                  device: str | None = None, nickname: str | None = None) -> None:
        self._exec("INSERT INTO audit(ts, device, nickname, entity, entity_id, action, before, after) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (time.time(), device, nickname, entity, entity_id, action,
                    None if before is None else json.dumps(before, ensure_ascii=False),
                    None if after is None else json.dumps(after, ensure_ascii=False)))

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM audit ORDER BY ts DESC LIMIT ?", (limit,))
        for r in rows:
            for k in ("before", "after"):
                r[k] = json.loads(r[k]) if r[k] else None
        return rows

    # ------------------------------------------------------------ bin
    def trash_put(self, entity: str, entity_id: str, data: Any,
                  device: str | None = None, nickname: str | None = None) -> int:
        cur = self._exec("INSERT INTO trash(ts, entity, entity_id, data, device, nickname) "
                         "VALUES (?,?,?,?,?,?)",
                         (time.time(), entity, entity_id, json.dumps(data, ensure_ascii=False),
                          device, nickname))
        return int(cur.lastrowid)

    def trash(self) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM trash ORDER BY ts DESC")
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    def trash_take(self, trash_id: int) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM trash WHERE id=?", (trash_id,))
        if not rows:
            return None
        self._exec("DELETE FROM trash WHERE id=?", (trash_id,))
        row = rows[0]
        row["data"] = json.loads(row["data"])
        return row

    # ------------------------------------------------------------ retention
    def purge(self, now: float | None = None) -> None:
        now = now or time.time()
        self._exec("DELETE FROM events WHERE ts < ?", (now - EVENT_RETENTION_S,))
        self._exec("DELETE FROM positions WHERE ts < ?", (now - POSITION_RETENTION_S,))
        self._exec("DELETE FROM trash WHERE ts < ?", (now - TRASH_RETENTION_S,))
