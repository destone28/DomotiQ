# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Plain data shared by the vision pipeline, the house state and the web app."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# Categories of things the house can see. Rules filter on them, and the
# "animal" group covers every pet species.
PERSON = "person"
DOG = "dog"
CAT = "cat"
ANIMAL = "animal"
CAR = "car"
OBJECT = "object"
CATEGORIES = (PERSON, DOG, CAT, ANIMAL, CAR, OBJECT)
ANIMALS = (DOG, CAT, ANIMAL)

CATEGORY_NAMES = {
    PERSON: {"it": "persona", "en": "person"},
    DOG: {"it": "cane", "en": "dog"},
    CAT: {"it": "gatto", "en": "cat"},
    ANIMAL: {"it": "animale", "en": "animal"},
    CAR: {"it": "auto", "en": "car"},
    OBJECT: {"it": "oggetto", "en": "object"},
}


def category_matches(category: str | None, wanted: str | None) -> bool:
    """True when `category` belongs to `wanted` ("animal" matches every pet)."""
    if not wanted or wanted == "any":
        return True
    if wanted == ANIMAL:
        return category in ANIMALS
    return category == wanted


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class Identity:
    """A registered character, pet, car or object."""

    id: str
    name: str
    category: str = PERSON
    alias_en: str | None = None          # how the English recognizer should hear it
    color: str = "#888888"               # dominant colour seen by the webcam, #rrggbb
    signature: list[float] = field(default_factory=list)   # colour signature (vision)
    photo: str | None = None             # file name under var/photos
    created_at: float = field(default_factory=time.time)
    created_by: str | None = None
    facts: list[str] = field(default_factory=list)   # "fa il medico", "ha paura dei ragni": used in the stories

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Identity":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})


@dataclass
class Track:
    """Something the house sees right now, with its position on the floor."""

    id: str
    x: float
    y: float
    category: str = OBJECT
    identity: str | None = None          # Identity.id when recognized
    room: str | None = None
    color: str = "#888888"
    confidence: float = 1.0
    uncertain: bool = False              # the house is not sure who this is
    candidates: list[str] = field(default_factory=list)
    carried: bool = False                # inside a visitor's hand right now
    moving: bool = False
    since: float = field(default_factory=time.time)
    virtual: bool = False                # created by the simulation
    hidden: bool = False                 # not seen for a moment, kept where it was
    presence: float = 1.0                # how sure the house is that something is really there (0-1)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["x"] = round(self.x, 1)
        d["y"] = round(self.y, 1)
        d["confidence"] = round(self.confidence, 2)
        return d
