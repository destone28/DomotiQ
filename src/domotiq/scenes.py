# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Scenes: a named way for the whole house to behave."""

from __future__ import annotations

from typing import Any

SCENES: dict[str, dict[str, Any]] = {
    "normal": {
        "name": {"it": "Normale", "en": "Normal"},
        "follow": True,
        "rooms": {},
    },
    "relax": {
        "name": {"it": "Relax", "en": "Relax"},
        "follow": True,
        "follow_color": "#ff8c3c",
        "follow_brightness": 30,
        "rooms": {},
    },
    "cinema": {
        "name": {"it": "Cinema", "en": "Cinema"},
        "follow": False,
        "rooms": {"living": {"effect": "solid", "color": "#2040ff", "brightness": 20}},
    },
    "night": {
        "name": {"it": "Notte", "en": "Night"},
        # a courtesy light: whoever gets up at night finds a dim warm light in the room
        "follow": True,
        "follow_color": "#ff7a30",
        "follow_brightness": 12,
        "rooms": {},
    },
    "away": {
        "name": {"it": "Via", "en": "Away"},
        "follow": False,
        "rooms": {},
    },
}

ORDER = ["normal", "cinema", "relax", "night", "away"]


def scene_name(scene: str, lang: str = "it") -> str:
    return SCENES.get(scene, SCENES["normal"])["name"].get(lang, scene)


def find_scene(text: str) -> str | None:
    """Match a spoken or typed scene name in either language."""
    t = (text or "").casefold()
    for sid, sc in SCENES.items():
        if sid in t or any(n.casefold() in t for n in sc["name"].values()):
            return sid
    aliases = {"sera": "relax", "evening": "relax", "film": "cinema", "movie": "cinema",
               "fuori": "away", "uscito": "away", "dormire": "night", "sleep": "night"}
    for word, sid in aliases.items():
        if word in t:
            return sid
    return None
