# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The empty house photographed in every light of the house.

With the house empty, its own lights are shown one after the other (all off, all on, one room at a time, the scenes)
and in each the vision keeps a picture of the empty house. When the light changes, the house compares with the one
taken in the light most like it, instead of learning the empty house again from what it sees (a figurine it does not
follow would become part of it). The lights of the hall, that the house does not command, are added one at a time
from Calibration ("add the light of now").
"""

from __future__ import annotations

import asyncio
from typing import Any

from .lights import LightRequest
from .scenes import SCENES, scene_name

CALIB = 92               # above the party and the rules, below the constraints of the firmware and the flash
SETTLE_S = 3.0           # the LEDs reach their colour, the webcam sees them steady
SWEEP_SCENES = ("cinema", "relax", "night")


def sweep_states(ctx: Any) -> list[tuple[str, dict[str, LightRequest]]]:
    """Every light of the house as a person in a room lights it, all of them, and the scenes: (label, requests)."""
    color = ctx.settings.get("lights.follow_color", "#ffaa5a")
    brightness = int(ctx.settings.get("lights.follow_brightness", 60))
    rooms = sorted({light.room for light in ctx.layout.lights.values()})
    on = {r: LightRequest("solid", color, brightness, priority=CALIB) for r in rooms}
    off = {r: LightRequest("off", "#000000", 0, priority=CALIB) for r in rooms}
    states = [("luci della casa spente", dict(off)), ("tutte le luci della casa", dict(on))]
    for r in rooms:
        states.append((f"luce: {r}", {**off, r: on[r]}))
    for sid in SWEEP_SCENES:
        lit = {room: LightRequest(req.get("effect", "solid"), req["color"], req.get("brightness", 40), priority=CALIB)
               for room, req in SCENES[sid].get("rooms", {}).items()}
        states.append((f"scenario: {scene_name(sid)}", {**off, **lit}))
    return states


async def photograph_lights(ctx: Any, settle_s: float = SETTLE_S, force: bool = False) -> dict[str, Any]:
    """Show each light of the house, wait for it to settle and keep the empty house in it. Stops at the first refusal
    (a figurine still on the house, unless `force`: somebody looked and it is no figurine; a webcam that sees too
    little). The lights go back as they were."""
    loop = asyncio.get_running_loop()
    done, refused = [], None
    try:
        for label, requests in sweep_states(ctx):
            ctx.lights.clear_prefix("calib")
            for room, req in requests.items():
                ctx.lights.set(room, "calib", req)
            await ctx.lights.refresh()
            await asyncio.sleep(settle_s)
            r = await loop.run_in_executor(None, lambda: ctx.vision.command("empty_add", label=label, force=force))
            if not r.get("ok"):
                refused = r
                break
            done.append(label)
    finally:
        ctx.lights.clear_prefix("calib")
        await ctx.lights.refresh()
    if refused is not None:
        return {**refused, "ok": False, "done": done}
    return {"ok": True, "done": done,
            "message": f"Casa vuota fotografata con {len(done)} luci della casa.",
            "message_en": f"Empty house photographed in {len(done)} lights of the house."}
