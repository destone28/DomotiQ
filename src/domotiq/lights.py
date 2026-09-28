# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Who decides the colour of each light.

Every light has a stack of layers: the follow-me light, the scene, the
rules, the party, the constraints, the language flash. The highest active
layer wins; when it expires or is cleared, the one below shows again. The
controller sends the firmware only the result, and only when it changes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from .bus import Bus
from .layout import Layout

EFFECTS = {
    "off": 0, "solid": 1, "breathe": 2, "blink": 3, "wave": 4, "rainbow": 5,
    "sparkle": 6, "fire": 7, "alarm": 8, "cool": 9, "warm": 10,
}

# layer priorities, highest wins
FOLLOW = 10
SCENE = 30
RULE = 50
PARTY = 90
CONSTRAINT = 95
FLASH = 99

NAMED_COLORS = {
    "white": "#ffffff", "warm": "#ffaa5a", "red": "#ff2010", "green": "#20e040",
    "blue": "#2050ff", "yellow": "#ffd020", "orange": "#ff8000", "purple": "#a030ff",
    "pink": "#ff40a0", "cyan": "#20d0ff", "off": "#000000",
}


def parse_color(value: str | None) -> tuple[int, int, int]:
    value = NAMED_COLORS.get((value or "").lower(), value or "#000000")
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except (ValueError, IndexError):
        return 255, 255, 255


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


class LightSink(Protocol):
    async def light(self, index: int, effect: int, r: int, g: int, b: int,
                    brightness: int, speed: int, duration_ms: int = 0) -> Any: ...


@dataclass
class LightRequest:
    effect: str = "solid"
    color: str = "#ffffff"
    brightness: int = 60          # relative to the house maximum, 0-100
    speed: int = 50
    priority: int = RULE
    expires: float | None = None  # absolute time, None = until cleared
    source: str = ""

    def key(self) -> tuple:
        return (self.effect, self.color.lower(), self.brightness, self.speed)

    def to_dict(self) -> dict[str, Any]:
        return {"effect": self.effect, "color": self.color, "brightness": self.brightness,
                "speed": self.speed, "source": self.source}


OFF = LightRequest(effect="off", color="#000000", brightness=0, priority=0, source="off")


class LightController:
    def __init__(self, layout: Layout, bus: Bus, sink: LightSink | None = None) -> None:
        self.layout = layout
        self.bus = bus
        self.sink = sink
        self.layers: dict[str, dict[str, LightRequest]] = {lid: {} for lid in layout.lights}
        self.sent: dict[str, tuple | None] = {lid: None for lid in layout.lights}
        self.party_until = 0.0

    # ------------------------------------------------------------ layers
    def _targets(self, light: str) -> list[str]:
        if light == "all":
            return list(self.layers)
        if light in self.layers:
            return [light]
        room_light = self.layout.light_of_room(light)
        return [room_light.id] if room_light else []

    def set(self, light: str, layer: str, request: LightRequest,
            duration_s: float | None = None) -> None:
        if duration_s:
            request.expires = time.time() + duration_s
        request.source = request.source or layer
        for lid in self._targets(light):
            self.layers[lid][layer] = LightRequest(**{**request.__dict__})

    def clear(self, light: str, layer: str) -> None:
        for lid in self._targets(light):
            self.layers[lid].pop(layer, None)

    def clear_prefix(self, prefix: str) -> None:
        for stack in self.layers.values():
            for name in [n for n in stack if n.startswith(prefix)]:
                stack.pop(name, None)

    def resolve(self, light: str, now: float | None = None) -> LightRequest:
        now = now or time.time()
        stack = self.layers[light]
        for name in [n for n, r in stack.items() if r.expires and r.expires <= now]:
            stack.pop(name, None)
        if not stack:
            return OFF
        return max(stack.values(), key=lambda r: r.priority)

    # ------------------------------------------------------------ output
    async def refresh(self, force: bool = False) -> None:
        """Send the firmware the lights whose result changed."""
        changed = {}
        for lid, light in self.layout.lights.items():
            req = self.resolve(lid)
            key = req.key()
            if force or key != self.sent[lid]:
                self.sent[lid] = key
                changed[lid] = req
                if self.sink is not None:
                    r, g, b = parse_color(req.color)
                    try:
                        await self.sink.light(light.index, EFFECTS.get(req.effect, 1),
                                              r, g, b, int(req.brightness), int(req.speed), 0)
                    except Exception:  # noqa: BLE001 - the MCU may be missing, the state is still right
                        self.sent[lid] = None
        if changed:
            self.bus.publish("lights_changed", lights=self.state())

    def state(self) -> dict[str, dict[str, Any]]:
        out = {}
        now = time.time()
        for lid in self.layout.lights:
            d = self.resolve(lid, now).to_dict()
            d["party"] = now < self.party_until
            out[lid] = d
        return out
