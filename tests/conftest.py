# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Shared fixtures: a whole house with no hardware, in a temporary folder."""

from __future__ import annotations

import pytest

from domotiq.bus import Bus
from domotiq.house import House
from domotiq.identities import Identities
from domotiq.layout import Layout
from domotiq.lights import LightController
from domotiq.mcu import SimulatedMcu
from domotiq.rules import RuleEngine
from domotiq.settings import Paths, Settings
from domotiq.store import Store


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def say(self, text, ctx):
        self.calls.append(("say", text.get("it") if isinstance(text, dict) else text, ctx))

    async def sound(self, name):
        self.calls.append(("sound", name))

    async def relay(self, on, duration_s):
        self.calls.append(("relay", on, duration_s))

    async def notify(self, level, text, ctx):
        self.calls.append(("notify", level, text, ctx))

    async def scene(self, scene):
        self.calls.append(("scene", scene))

    async def party(self):
        self.calls.append(("party",))

    async def grill(self):
        self.calls.append(("grill",))

    def kinds(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture
def layout() -> Layout:
    return Layout.load()


@pytest.fixture
def env(tmp_path, layout):
    paths = Paths(tmp_path / "var")
    settings = Settings(paths)
    store = Store(paths.db)
    bus = Bus()
    mcu = SimulatedMcu()
    lights = LightController(layout, bus, mcu)
    identities = Identities(paths, store, bus)
    house = House(layout, bus, identities, lights, settings, store)
    executor = RecordingExecutor()
    rules = RuleEngine(paths, bus, house, lights, store, executor)

    class Env:
        pass

    e = Env()
    e.paths, e.settings, e.store, e.bus, e.mcu = paths, settings, store, bus, mcu
    e.lights, e.identities, e.house, e.rules, e.executor, e.layout = (
        lights, identities, house, rules, executor, layout)
    yield e
    store.close()
