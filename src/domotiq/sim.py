# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The simulation: virtual characters dragged on the plan, virtual sensors.

While it is on, the house believes the virtual scene instead of the webcam.
Lights, voice and rules react exactly as they would to real figurines, which
is how the whole house is developed and demonstrated without hardware.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .model import OBJECT, PERSON, Track, new_id


@dataclass
class VirtualObject:
    id: str
    x: float
    y: float
    category: str = PERSON
    identity: str | None = None
    color: str = "#e03030"
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Simulation:
    enabled: bool = False
    mute: bool = False               # lights and voice of the real house stay quiet
    objects: dict[str, VirtualObject] = field(default_factory=dict)
    changed_at: float = 0.0

    def add(self, x: float, y: float, category: str = PERSON, identity: str | None = None,
            color: str = "#e03030", name: str = "") -> VirtualObject:
        obj = VirtualObject(new_id("v"), float(x), float(y), category or OBJECT, identity, color, name)
        self.objects[obj.id] = obj
        self.changed_at = time.time()
        return obj

    def move(self, obj_id: str, x: float, y: float) -> VirtualObject | None:
        obj = self.objects.get(obj_id)
        if obj:
            obj.x, obj.y = float(x), float(y)
            self.changed_at = time.time()
        return obj

    def remove(self, obj_id: str) -> bool:
        self.changed_at = time.time()
        return self.objects.pop(obj_id, None) is not None

    def clear(self) -> None:
        self.objects.clear()
        self.changed_at = time.time()

    def tracks(self) -> list[Track]:
        return [Track(id=o.id, x=o.x, y=o.y, category=o.category, identity=o.identity,
                      color=o.color, virtual=True) for o in self.objects.values()]

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "mute": self.mute,
                "objects": [o.to_dict() for o in self.objects.values()]}
