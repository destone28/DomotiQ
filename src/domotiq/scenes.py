# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Scenes: a named way for the whole house to behave."""

from __future__ import annotations

from typing import Any

SCENES: dict[str, dict[str, Any]] = {
    # every scene looks different at a glance, people in the house or not
    "normal": {
        "name": {"it": "Normale", "en": "Normal"},
        # the lights follow people, in their favourite colour if they told it
        "follow": True,
        "rooms": {},
    },
    "cinema": {
        "name": {"it": "Cinema", "en": "Cinema"},
        # the flickering glow of a screen in the living room, every other room dark
        "follow": False,
        "rooms": {"living": {"effect": "sparkle", "color": "#3a5cff", "brightness": 30}},
    },
    "relax": {
        "name": {"it": "Relax", "en": "Relax"},
        # a fire in the living room, a soft warm light breathing in the bedroom, dim warm lights where people are
        "follow": True,
        "follow_color": "#ff8c3c",
        "follow_brightness": 30,
        "rooms": {"living": {"effect": "fire", "color": "#ff5a00", "brightness": 45},
                  "bedroom": {"effect": "breathe", "color": "#ff8c3c", "brightness": 22}},
    },
    "night": {
        "name": {"it": "Notte", "en": "Night"},
        # dark, with a small night light in the bathroom; whoever gets up finds a dim warm light in the room
        "follow": True,
        "follow_color": "#ff7a30",
        "follow_brightness": 12,
        "rooms": {"bathroom": {"effect": "solid", "color": "#ff7a30", "brightness": 8}},
    },
    "away": {
        "name": {"it": "Via", "en": "Away"},
        # nobody home: one room at a time lights up for a while, as if somebody were in (an intruder sets the alarm
        # off, see default_rules.py)
        "follow": False,
        "rooms": {},
        "simulate": {"rooms": ["kitchen", "living", "bedroom", "bathroom"], "color": "#ffb060", "brightness": 45,
                     "every_s": (15.0, 30.0)},
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
