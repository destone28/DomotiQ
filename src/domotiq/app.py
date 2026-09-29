# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The house application: puts every part together and runs it.

    python -m domotiq                 on the UNO Q (the systemd service)
    python -m domotiq --simulate      on a PC, with no hardware at all

A missing part never stops the house: without the MCU the lights are only
drawn on the web plan, without the camera the simulation feeds the tracks,
without the audio card the house writes what it would say.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass
from typing import Any

from . import __version__
from .activities import Actions
from .auth import StaffAuth
from .bus import Bus, Event
from .clock import HouseClock
from .house import House
from .identities import Identities
from .layout import Layout
from .lights import LightController
from .mcu import Mcu, RouterClient, SimulatedMcu
from .registration import Registration
from .rules import RuleEngine
from .settings import Paths, Settings
from .sim import Simulation
from .store import Store
from .vision.link import NoVision, VisionLink

log = logging.getLogger("domotiq")


@dataclass
class Context:
    args: argparse.Namespace
    paths: Paths
    settings: Settings
    layout: Layout
    store: Store
    bus: Bus
    identities: Identities
    mcu: Mcu
    lights: LightController
    house: House
    rules: RuleEngine
    actions: Actions
    auth: StaffAuth
    clock: HouseClock
    sim: Simulation
    vision: VisionLink
    registration: Registration | None = None
    audio: Any = None
    voice: Any = None
    classifier: Any = None
    started: float = 0.0
    version: str = __version__


def build(args: argparse.Namespace) -> Context:
    paths = Paths(args.var)
    settings = Settings(paths)
    layout = Layout.load()
    store = Store(paths.db)
    bus = Bus()
    identities = Identities(paths, store, bus)
    if args.simulate or args.no_mcu:
        mcu: Mcu = SimulatedMcu()
    else:
        mcu = Mcu(RouterClient(args.router))
    lights = LightController(layout, bus, mcu)
    house = House(layout, bus, identities, lights, settings, store)
    sim = Simulation(enabled=bool(args.simulate))
    ctx = Context(args=args, paths=paths, settings=settings, layout=layout, store=store, bus=bus,
                  identities=identities, mcu=mcu, lights=lights, house=house,
                  rules=None, actions=None, auth=StaffAuth(settings),  # type: ignore[arg-type]
                  clock=HouseClock(can_set=not args.simulate), sim=sim, vision=NoVision())
    ctx.actions = Actions(ctx)
    ctx.rules = RuleEngine(paths, bus, house, lights, store, ctx.actions)
    ctx.registration = Registration(ctx)
    house.status["simulation"] = sim.enabled
    return ctx


def _optional_parts(ctx: Context) -> None:
    """Audio, voice, vision and the photo classifier: each one may be missing."""
    args = ctx.args
    if not args.no_audio:
        try:
            from .audio.output import Audio
            ctx.audio = Audio(ctx.settings, device=args.audio_device, dry=args.simulate and not args.audio)
            ctx.house.status["audio"] = ctx.audio.ok
        except Exception as e:  # noqa: BLE001
            log.warning("audio not available: %s", e)
    try:
        from .voice.manager import Voice
        ctx.voice = Voice(ctx)
    except Exception as e:  # noqa: BLE001
        log.warning("voice not available: %s", e)
    if not args.no_camera and (not args.simulate or args.camera):
        try:
            from .vision.worker import VisionProcess
            ctx.vision = VisionProcess(ctx.paths, ctx.layout, ctx.settings, ctx.identities, device=args.camera)
            ctx.house.status["camera"] = True
        except Exception as e:  # noqa: BLE001
            log.warning("vision not available: %s", e)
    try:
        from .vision.classify import PhotoClassifier
        ctx.classifier = PhotoClassifier(ctx.paths.models)
    except Exception as e:  # noqa: BLE001
        log.info("photo classifier not available: %s", e)


# ==================================================================== wiring
def _wire(ctx: Context) -> None:
    bus = ctx.bus

    async def on_button(ev: Event) -> None:
        button, pressed = ev.get("button"), ev.get("pressed")
        if button == "language" and pressed:
            await ctx.actions.toggle_language()
        elif button == "talk" and ctx.voice is not None:
            await ctx.voice.talk_button(pressed)
        elif button == "intercom" and pressed and ctx.voice is not None:
            await ctx.voice.intercom()

    bus.subscribe("button", on_button)

    def record(ev: Event) -> None:
        if ev.type in ("room_enter", "room_exit"):
            if ev.get("category") in ("person", "car", "dog", "cat", "animal"):
                ctx.store.add_event(ev.type, {k: ev.get(k) for k in ("track", "identity", "name",
                                                                      "category", "room", "other")})
        elif ev.type in ("car", "climate", "shower", "scene", "registered", "language"):
            ctx.store.add_event(ev.type, dict(ev.data))
        elif ev.type in ("grill", "party") and ev.get("state") in ("started", "ready", "ended"):
            ctx.store.add_event(ev.type, dict(ev.data))
        elif ev.type == "say":
            ctx.store.add_event("say", dict(ev.data))

    for t in ("room_enter", "room_exit", "car", "climate", "shower", "scene", "registered",
              "language", "grill", "party", "say"):
        bus.subscribe(t, record)
    _wire_vision(ctx)


def _wire_vision(ctx: Context) -> None:
    """Questions of the vision about who is who, and the lights it must know about."""
    bus = ctx.bus
    if hasattr(ctx.vision, "on_question"):
        # called from the thread that reads the vision process: the bus brings it to the loop
        ctx.vision.on_question = lambda track, cands: bus.publish(
            "vision_question", track=track.to_dict(), candidates=list(cands))

    def ask_who(ev: Event) -> None:
        from .voice.answers import room as room_phrase
        track = ev.get("track") or {}
        cands = [c for c in ev.get("candidates") or [] if ctx.identities.get(c)]
        if len(cands) < 2 or not track.get("id"):
            return
        if any(c["context"].get("kind") == "who" and c["context"].get("track") == track["id"]
               for c in ctx.house.confirmations.values()):
            return
        names = [ctx.identities.name_of(c) for c in cands]
        where_it = room_phrase(ctx, track.get("room"), "it")
        where_en = room_phrase(ctx, track.get("room"), "en")
        question = {"it": f"{where_it[0].upper()}{where_it[1:]} c'è {' o '.join(names)}?",
                    "en": f"Is it {' or '.join(names)} {where_en}?"}
        options = [{"value": c, "label": {"it": n, "en": n}} for c, n in zip(cands, names)]
        ctx.house.ask(question, options, {"kind": "who", "track": track["id"]}, timeout_s=60)

    def answered(ev: Event) -> None:
        c = ev.get("context") or {}
        if c.get("kind") == "who" and ev.get("value"):
            ctx.vision.assign(c["track"], ev.get("value"))

    last: dict[str, Any] = {}

    def lights(ev: Event) -> None:
        state = ev.get("lights") or {}
        rooms = []
        for lid, st in state.items():
            if last.get(lid) != st:
                light = ctx.layout.lights.get(lid)
                if light:
                    rooms.append(light.room)
            last[lid] = st
        if rooms:
            ctx.vision.lights_changed(rooms)

    bus.subscribe("vision_question", ask_who)
    bus.subscribe("confirm_answer", answered)
    bus.subscribe("lights_changed", lights)


async def on_mcu_notify(ctx: Context, name: str, params: list[Any]) -> None:
    if ctx.sim.enabled and ctx.sim.mute:
        return
    if name == "btn" and len(params) >= 2:
        ctx.house.on_button(int(params[0]), bool(params[1]))
    elif name == "dist" and params:
        if not ctx.sim.enabled:
            ctx.house.on_distance(int(params[0]))
    elif name == "thermo" and len(params) >= 3:
        if not ctx.sim.enabled:
            ctx.house.on_thermo(int(params[0]), params[1] / 100.0, params[2] / 100.0)
    elif name == "mods" and params:
        ctx.mcu.set_modules(int(params[0]))
        ctx.house.status["modules"] = ctx.mcu.modules
        ctx.bus.publish("modules", modules=ctx.mcu.modules)


# ==================================================================== loops
async def periodic(ctx: Context) -> None:
    last_check = 0.0
    last_purge = 0.0
    silent_since: float | None = None     # the router answers but the sketch does not
    resets: list[float] = []
    clock_warned = False
    while True:
        now = time.time()
        try:
            if ctx.sim.enabled:
                # every tick, even with nothing moved: dwell and count timers need the time to pass
                ctx.house.update_tracks(ctx.sim.tracks(), now)
            elif ctx.vision.available:
                ctx.house.update_tracks(ctx.vision.tracks(), now)
            ctx.house.tick(now)
            ctx.rules.tick(now)
            ctx.house.expire_confirmations(now)
            if ctx.registration:
                ctx.registration.poll()
            if not (ctx.sim.enabled and ctx.sim.mute):
                await ctx.lights.refresh()
            if now - last_check > 5:
                last_check = now
                was = ctx.mcu.ok
                ok = await ctx.mcu.check()
                ctx.house.status["mcu"] = ok
                ctx.house.status["modules"] = ctx.mcu.modules
                if ok and not was:
                    await _mcu_ready(ctx)
                client = ctx.mcu.client
                if ok or ctx.mcu.version is not None or not isinstance(client, RouterClient) \
                        or not client.connected.is_set():
                    silent_since = None
                elif silent_since is None:
                    silent_since = now
                elif now - silent_since > 8 and len(resets) < 3 and (not resets or now - resets[-1] > 60):
                    # typically after a reboot of Linux: restart the sketch now that the router listens
                    resets.append(now)
                    silent_since = None
                    log.warning("the microcontroller does not answer: resetting it (attempt %d)", len(resets))
                    await ctx.mcu.reset()
                if ctx.voice is not None:
                    ctx.house.status["llm"] = getattr(ctx.voice, "llm_ok", False)
                if ctx.audio is not None:
                    ctx.house.status["audio"] = ctx.audio.ok
                ctx.house.status["camera"] = ctx.vision.available
                if ctx.vision.available and ctx.vision.status().get("moved"):
                    ctx.house.set_alert("camera-moved", name={"it": "La webcam si è spostata: rifare la calibrazione",
                                                              "en": "The webcam has moved: calibrate again"})
                else:
                    ctx.house.clear_alert("camera-moved")
                ctx.bus.publish("status", **ctx.house.status)
            if not clock_warned and not ctx.clock.known and now - ctx.started > 120:
                clock_warned = True
                await ctx.actions.say({"it": "Non so che ore sono: premi Parla e dimmelo.",
                                       "en": "I don't know what time it is: press Talk and tell me."})
            if now - last_purge > 3600:
                last_purge = now
                ctx.store.purge(now)
        except Exception:  # noqa: BLE001 - the loop must never die
            log.exception("periodic step failed")
        await asyncio.sleep(0.2)


async def _mcu_ready(ctx: Context) -> None:
    cfg = ctx.settings.get("lights")
    try:
        await ctx.mcu.limits(cfg["max_brightness"], cfg["current_budget_ma"])
        await ctx.mcu.relay(False)
        await ctx.lights.refresh(force=True)
        await ctx.actions.update_leds()
    except Exception:  # noqa: BLE001
        log.warning("MCU setup after connection failed")


async def serve(ctx: Context) -> None:
    import uvicorn

    from .web.server import create_app

    loop = asyncio.get_running_loop()
    ctx.bus.bind(loop)
    ctx.started = time.time()
    if isinstance(ctx.mcu.client, RouterClient):
        ctx.mcu.client.on_notify = lambda n, p: on_mcu_notify(ctx, n, p)
        ctx.mcu.client.start()
    _wire(ctx)
    if ctx.voice is not None:
        await ctx.voice.start()
    if ctx.audio is not None:
        ctx.audio.start()
    tasks = [asyncio.create_task(periodic(ctx))]
    app = create_app(ctx)
    config = uvicorn.Config(app, host=ctx.args.host, port=ctx.args.port, log_level="warning",
                            access_log=False, ws_ping_interval=20, ws_ping_timeout=20)
    server = uvicorn.Server(config)
    log.info("DomotiQ %s listening on http://%s:%s (simulation %s)", __version__,
             ctx.args.host, ctx.args.port, "on" if ctx.sim.enabled else "off")

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    server_task = asyncio.create_task(server.serve())
    await asyncio.wait([server_task, asyncio.create_task(stop.wait())],
                       return_when=asyncio.FIRST_COMPLETED)
    server.should_exit = True
    try:
        # let uvicorn close its connections and its lifespan by itself
        await asyncio.wait_for(server_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    for t in tasks:
        t.cancel()
    await _shutdown(ctx)


async def _shutdown(ctx: Context) -> None:
    try:
        await ctx.mcu.relay(False)
    except Exception:  # noqa: BLE001
        pass
    if ctx.voice is not None:
        await ctx.voice.stop()
    if ctx.audio is not None:
        ctx.audio.stop()
    ctx.vision.stop()
    ctx.store.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="domotiq", description="DomotiQ smart home diorama")
    p.add_argument("--simulate", action="store_true", help="no hardware: virtual scene, virtual MCU")
    p.add_argument("--host", default=os.environ.get("DOMOTIQ_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DOMOTIQ_PORT", "8080")))
    p.add_argument("--var", default=os.environ.get("DOMOTIQ_VAR"), help="data folder")
    p.add_argument("--router", default="/run/arduino-router.sock")
    p.add_argument("--no-mcu", action="store_true")
    p.add_argument("--no-camera", action="store_true")
    p.add_argument("--camera", default=None,
                   help="webcam device (default: found by name); 'synthetic' renders a house with figurines")
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--audio", action="store_true", help="play sound even in simulation")
    p.add_argument("--audio-device", default=os.environ.get("DOMOTIQ_AUDIO"))
    p.add_argument("--no-voice", action="store_true")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ctx = build(args)
    _optional_parts(ctx)
    asyncio.run(serve(ctx))


if __name__ == "__main__":
    main()
