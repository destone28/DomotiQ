# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The house layout: rooms, walls, doors, furniture, lights and sensors.

Everything is expressed in millimetres on the floor plane of the diorama:
x grows from the left side (0) to the right side (650), y is 0 at the facade,
negative on the driveway and grows towards the back of the house (370).
The same data drives the web plan, the vision pipeline and the rules.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_LAYOUT = DATA_DIR / "house.json"

OUTSIDE = "outside"


@dataclass(frozen=True)
class Rect:
    x0: float
    x1: float
    y0: float
    y1: float

    @classmethod
    def of(cls, values: Iterable[float]) -> "Rect":
        x0, x1, y0, y1 = values
        return cls(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1))

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        return (self.x0 - margin <= x <= self.x1 + margin
                and self.y0 - margin <= y <= self.y1 + margin)

    def distance(self, x: float, y: float) -> float:
        """Distance from the point to the rectangle, 0 when inside."""
        dx = max(self.x0 - x, 0.0, x - self.x1)
        dy = max(self.y0 - y, 0.0, y - self.y1)
        return math.hypot(dx, dy)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def as_list(self) -> list[float]:
        return [self.x0, self.x1, self.y0, self.y1]


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        return math.hypot(x - self.cx, y - self.cy) <= self.r + margin


def _shape(item: dict) -> Rect | Circle:
    if "circle" in item:
        return Circle(*item["circle"])
    return Rect.of(item["rect"])


@dataclass(frozen=True)
class Room:
    id: str
    name: dict[str, str]
    rect: Rect
    indoor: bool
    light: str | None
    private: bool = False

    def label(self, lang: str = "it") -> str:
        return self.name.get(lang) or self.name.get("it") or self.id


@dataclass(frozen=True)
class Door:
    id: str
    rooms: tuple[str, str]
    rect: Rect
    main: bool = False
    vehicles: bool = False


@dataclass(frozen=True)
class Light:
    id: str
    room: str
    index: int
    channel: int
    rect: Rect


@dataclass
class Layout:
    """The parsed content of data/house.json, with geometric helpers."""

    raw: dict[str, Any]
    base: Rect
    view: Rect
    camera: tuple[float, float, float]
    rooms: dict[str, Room] = field(default_factory=dict)
    doors: list[Door] = field(default_factory=list)
    lights: dict[str, Light] = field(default_factory=dict)
    excluded: list[Rect | Circle] = field(default_factory=list)
    parking: Rect | None = None

    # ------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: Path | str = DEFAULT_LAYOUT) -> "Layout":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Layout":
        cam = data["camera"]
        layout = cls(raw=data, base=Rect.of(data["base"]), view=Rect.of(data["view"]),
                     camera=(cam["x"], cam["y"], cam["height"]))
        for r in data["rooms"]:
            layout.rooms[r["id"]] = Room(r["id"], r["name"], Rect.of(r["rect"]),
                                         r.get("indoor", True), r.get("light"),
                                         r.get("private", False))
        for d in data["doors"]:
            layout.doors.append(Door(d["id"], tuple(d["rooms"]), Rect.of(d["rect"]),
                                     d.get("main", False), d.get("vehicles", False)))
        for li in data["lights"]:
            layout.lights[li["id"]] = Light(li["id"], li["room"], li["index"],
                                            li["channel"], Rect.of(li["rect"]))
        layout.excluded = [_shape(e) for e in data.get("excluded", [])]
        if data.get("parking"):
            layout.parking = Rect.of(data["parking"])
        return layout

    # ------------------------------------------------------------ queries
    def room_at(self, x: float, y: float) -> str | None:
        """The room that strictly contains the point, if any."""
        for room in self.rooms.values():
            if room.rect.contains(x, y):
                return room.id
        return None

    def door_at(self, x: float, y: float, margin: float = 0.0) -> Door | None:
        for door in self.doors:
            if door.rect.contains(x, y, margin):
                return door
        return None

    def locate(self, x: float, y: float, previous: str | None = None,
               hysteresis: float = 15.0) -> str:
        """The room a floor point belongs to, with hysteresis on doorways.

        Someone standing on a threshold must not flicker between two rooms,
        so the previous room is kept until the point is clearly inside a new
        one. Points in the thickness of a wall or in a doorway keep the
        previous room when it is one of the two sides; points outside the
        base are "outside".
        """
        if previous in self.rooms and self.rooms[previous].rect.contains(x, y, hysteresis):
            return previous
        room = self.room_at(x, y)
        if room:
            return room
        door = self.door_at(x, y, 2.0)
        if door:
            if previous in door.rooms:
                return previous
            return door.rooms[0] if door.rooms[0] != OUTSIDE else door.rooms[1]
        if not self.base.contains(x, y):
            return OUTSIDE
        # inside a wall: the nearest room
        return min(self.rooms.values(), key=lambda r: r.rect.distance(x, y)).id

    def is_excluded(self, x: float, y: float, margin: float = 0.0) -> bool:
        return any(shape.contains(x, y, margin) for shape in self.excluded)

    def in_parking(self, x: float, y: float) -> bool:
        return bool(self.parking and self.parking.contains(x, y))

    def entrance(self) -> Door | None:
        return next((d for d in self.doors if d.main), None)

    def light_of_room(self, room: str) -> Light | None:
        r = self.rooms.get(room)
        return self.lights.get(r.light) if r and r.light else None

    def room_label(self, room: str, lang: str = "it") -> str:
        if room == OUTSIDE:
            return {"it": "fuori casa", "en": "outside"}.get(lang, "outside")
        r = self.rooms.get(room)
        return r.label(lang) if r else room

    def indoor_rooms(self) -> list[str]:
        return [r.id for r in self.rooms.values() if r.indoor]

    def to_dict(self) -> dict[str, Any]:
        return self.raw
