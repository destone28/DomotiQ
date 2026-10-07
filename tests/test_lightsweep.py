# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The empty house photographed in every light of the house (lightsweep.py)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from domotiq.bus import Bus
from domotiq.layout import Layout
from domotiq.lights import LightController, LightRequest


class _Settings:
    def get(self, dotted, default=None):
        return {"lights.follow_color": "#ffaa5a", "lights.follow_brightness": 60}.get(dotted, default)


class _Vision:
    """Keeps what the lights were each time the empty house was photographed."""

    def __init__(self, lights, refuse_at=None):
        self.lights, self.refuse_at, self.taken = lights, refuse_at, []

    def command(self, name, **params):
        assert name == "empty_add"
        if params["label"] == self.refuse_at:
            return {"ok": False, "error": "figurines", "message": "Sulla casa vedo ancora: Viola."}
        lit = sorted(lid for lid, st in self.lights.state().items() if st["effect"] != "off")
        self.taken.append((params["label"], lit))
        return {"ok": True}


def _ctx(refuse_at=None):
    layout = Layout.load()
    lights = LightController(layout, Bus())
    return SimpleNamespace(layout=layout, lights=lights, settings=_Settings(), vision=_Vision(lights, refuse_at))


def test_the_empty_house_is_photographed_in_every_light_of_the_house():
    from domotiq.lightsweep import photograph_lights
    ctx = _ctx()
    ctx.lights.set("kitchen", "follow", LightRequest("solid", "#ffffff", 60, priority=10))   # somebody in the kitchen
    r = asyncio.run(photograph_lights(ctx, settle_s=0.0))
    assert r["ok"]
    taken = dict(ctx.vision.taken)
    rooms = sorted(light.room for light in ctx.layout.lights.values())
    assert taken["luci della casa spente"] == []
    assert taken["tutte le luci della casa"] == sorted(ctx.layout.lights)
    for room in rooms:
        assert taken[f"luce: {room}"] == [ctx.layout.light_of_room(room).id]
    assert taken["scenario: Cinema"] == ["living"]
    # the lights of the house are back as they were
    st = ctx.lights.state()
    assert st["kitchen"]["effect"] == "solid" and all(v["effect"] == "off" for k, v in st.items() if k != "kitchen")


def test_a_figurine_on_the_house_stops_the_photographs():
    from domotiq.lightsweep import photograph_lights
    ctx = _ctx(refuse_at="tutte le luci della casa")
    r = asyncio.run(photograph_lights(ctx, settle_s=0.0))
    assert not r["ok"] and r["done"] == ["luci della casa spente"] and "Viola" in r["message"]
    assert all(v["effect"] == "off" for v in ctx.lights.state().values())
