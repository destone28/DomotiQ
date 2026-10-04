# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""HTTP API, WebSocket and static files of the web app.

Every phone gets the full state when it connects and then only the changes.
Anyone connected can do everything: look, command, edit rules, register
characters, calibrate, check and change the settings. Every change says which
phone made it (a random id kept by the browser, and an optional nickname),
and ends up in the change log on the device; deleted rules and characters
wait in the bin for 24 hours.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..identities import NameTaken, clean_name
from ..model import CATEGORIES, CATEGORY_NAMES, new_id
from ..rules import RuleError
from ..scenes import ORDER as SCENE_ORDER
from ..scenes import SCENES
from . import placeholder, sign

if TYPE_CHECKING:
    from ..app import Context

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"


def asset_version() -> str:
    """Changes whenever a file of the web app changes: the pages load their files under it, so a phone never
    keeps an old script after an update."""
    h = hashlib.sha1()
    for p in sorted(STATIC.rglob("*")):
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(STATIC)}:{st.st_mtime_ns}:{st.st_size}".encode())
    return h.hexdigest()[:10]


def page(name: str) -> Response:
    html = (STATIC / name).read_text(encoding="utf-8").replace('"/static/', f'"/static/v{asset_version()}/')
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


class FreshStatic(StaticFiles):
    """The files of the web app are checked again at every load (a cheap "not modified" when unchanged): after
    an update a phone never mixes the new page with old scripts kept in its cache."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response
MAX_PHOTO = 4 * 1024 * 1024


class Who:
    def __init__(self, request: Request) -> None:
        self.device = (request.headers.get("x-device") or "")[:40] or None
        nick = request.headers.get("x-nickname") or ""
        self.nickname = urllib.parse.unquote(nick)[:30] or None
        self.client = request.client.host if request.client else "?"


def who(request: Request) -> Who:
    return Who(request)


SAME_PHONE_S = 2 * 3600      # a new phone id from an address seen within this time is not greeted again


class Hub:
    """Fans out the house events to every connected phone (and a few to one phone only)."""

    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        self.clients: set[asyncio.Queue] = set()
        self.devices: dict[str, set[asyncio.Queue]] = {}      # phone id -> its open connections
        self.addresses: dict[str, float] = {}                 # address on the hotspot -> last phone seen there
        self._tracks_pending = False
        self._last_tracks = 0.0
        for t in ("tracks_changed", "lights_changed", "sensor", "count_changed", "alerts_changed",
                  "confirm", "confirm_closed", "notify", "say", "identities_changed", "rules_changed",
                  "scene", "party", "grill", "registration", "status", "language", "verbosity",
                  "volume", "car", "rule_fired", "climate", "shower", "armed",
                  "modules", "listening", "clock", "sim", "follow", "welcome"):
            ctx.bus.subscribe(t, self.on_event)

    def send(self, msg: dict[str, Any], to: set[asyncio.Queue] | None = None) -> None:
        data = json.dumps(msg, ensure_ascii=False, default=str)
        for q in list(self.clients if to is None else to):
            if q.qsize() > 200:
                continue          # a stuck phone must not grow the memory
            q.put_nowait(data)

    def attach(self, device: str, q: asyncio.Queue) -> None:
        self.devices.setdefault(device, set()).add(q)

    def detach(self, device: str, q: asyncio.Queue) -> None:
        qs = self.devices.get(device)
        if qs is not None:
            qs.discard(q)
            if not qs:
                self.devices.pop(device, None)

    def on_event(self, ev) -> None:
        h = self.ctx.house
        t = ev.type
        if t == "tracks_changed":
            now = time.time()
            if now - self._last_tracks >= 0.2:
                self._last_tracks = now
                self.send({"type": "tracks", "data": ev.get("tracks")})
            elif not self._tracks_pending:
                self._tracks_pending = True
                try:
                    asyncio.get_running_loop().call_later(0.2, self._flush_tracks)
                except RuntimeError:          # outside the loop (tests, tools): send now
                    self._flush_tracks()
        elif t == "lights_changed":
            self.send({"type": "lights", "data": self.ctx.lights.state()})
        elif t in ("sensor", "climate", "shower"):
            self.send({"type": "sensors", "data": {"sensors": h.sensors, "climate": h.climate,
                                                   "shower": h.shower}})
        elif t == "count_changed":
            self.send({"type": "counts", "data": h.counts})
        elif t == "alerts_changed":
            self.send({"type": "alerts", "data": list(h.alerts.values())})
        elif t in ("confirm", "confirm_closed"):
            self.send({"type": "confirmations", "data": h.snapshot()["confirmations"]})
        elif t in ("notify", "say", "rule_fired", "listening"):
            self.send({"type": t, "data": ev.data, "ts": ev.ts})
        elif t == "identities_changed":
            self.send({"type": "identities", "data": self.ctx.identities.to_list()})
        elif t == "rules_changed":
            self.send({"type": "rules", "data": self.ctx.rules.to_list()})
        elif t in ("scene", "party", "grill", "car", "language", "verbosity", "volume", "armed"):
            self.send({"type": "house", "data": _brief(self.ctx), "event": t, "detail": ev.data})
        elif t == "registration":
            self.send({"type": "registration", "data": ev.data})
        elif t in ("status", "modules"):
            self.send({"type": "status", "data": h.status})
        elif t == "sim":
            self.send({"type": "sim", "data": self.ctx.sim.to_dict()})
        elif t == "clock":
            self.send({"type": "clock", "data": self.ctx.clock.to_dict()})
        elif t == "follow":
            self.send({"type": "follow", "data": {"on": ev.get("on")}})
        elif t == "welcome":
            # the welcome of a new phone goes to that phone only
            qs = self.devices.get(ev.get("device") or "")
            if qs:
                self.send({"type": "welcome", "data": ev.data}, to=qs)

    def _flush_tracks(self) -> None:
        self._tracks_pending = False
        self._last_tracks = time.time()
        self.send({"type": "tracks", "data": [t.to_dict() for t in self.ctx.house.tracks.values()]})


def _brief(ctx: "Context") -> dict[str, Any]:
    h = ctx.house
    return {"scene": h.scene, "party": h.party_on, "grill": h.grill_on, "car": h.car_state(),
            "language": ctx.settings.get("voice.language"), "armed": h.armed,
            "verbosity": ctx.settings.get("voice.verbosity"), "volume": ctx.settings.get("voice.volume")}


def full_state(ctx: "Context") -> dict[str, Any]:
    s = ctx.house.snapshot()
    s.update({
        "version": ctx.version,
        "house": ctx.settings.get("house"),
        "layout": ctx.layout.to_dict(),
        "identities": ctx.identities.to_list(),
        "rules": ctx.rules.to_list(),
        "scenes": {k: {"name": v["name"]} for k, v in SCENES.items()},
        "scene_order": SCENE_ORDER,
        "categories": {c: CATEGORY_NAMES[c] for c in CATEGORIES},
        "clock": ctx.clock.to_dict(),
        "sim": ctx.sim.to_dict(),
        "registrations": ctx.registration.list() if ctx.registration else [],
        "brief": _brief(ctx),
        "camera": ctx.vision.available,
        "follow": ctx.settings.get("lights.follow", True),
    })
    return s


def create_app(ctx: "Context") -> FastAPI:
    app = FastAPI(title="DomotiQ", docs_url=None, redoc_url=None, openapi_url=None)
    hub = Hub(ctx)
    app.state.hub = hub
    ctx.hub_clients = hub.clients          # Diagnostics counts the phones with the web app open

    def audit(w: Who, entity: str, eid: str | None, action: str, before: Any = None, after: Any = None):
        ctx.store.add_audit(entity, eid, action, before, after, w.device, w.nickname)

    # ============================================================ pages
    @app.get("/", include_in_schema=False)
    async def index():
        return page("index.html")

    @app.get("/sign", include_in_schema=False)
    async def sign_page():
        return page("sign.html")

    @app.get("/board", include_in_schema=False)
    async def board_page():
        return page("board.html")

    @app.get("/static/v{version}/{path:path}", include_in_schema=False)
    async def versioned(version: str, path: str):
        """The files of the web app under the version of the moment: kept by the phones as long as they like."""
        f = (STATIC / path).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest():
        name = ctx.settings.get("house.name", {}).get("it", "DomotiQ")
        return JSONResponse({
            "name": f"DomotiQ – {name}", "short_name": "DomotiQ", "start_url": "/",
            "display": "standalone", "background_color": "#f6f7f5", "theme_color": "#00878f",
            "icons": [{"src": "/static/icons/icon.svg", "sizes": "any", "type": "image/svg+xml"},
                      {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"}],
        }, media_type="application/manifest+json")

    # ============================================================ state
    @app.get("/api/state")
    async def state():
        return full_state(ctx)

    @app.get("/api/events")
    async def events(limit: int = 100, before: float | None = None, types: str | None = None):
        return ctx.store.events(min(limit, 500), before, types.split(",") if types else None)

    @app.get("/api/audit")
    async def audit_log(limit: int = 100):
        return ctx.store.audit(min(limit, 500))

    @app.get("/api/history/{identity}")
    async def history(identity: str, hours: float = 24):
        since = time.time() - hours * 3600
        return {"rooms": ctx.store.room_changes(identity, since)}

    @app.post("/api/time")
    async def set_time(body: dict):
        epoch = float(body.get("epoch", 0))
        if epoch < 1.7e9:
            raise HTTPException(400, "bad time")
        changed = ctx.clock.set(epoch, "phone")
        if changed:
            ctx.bus.publish("clock", **ctx.clock.to_dict())
        return {"changed": changed, "clock": ctx.clock.to_dict()}

    # ============================================================ websocket
    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        # a browser cannot add headers to a websocket: the phone says who it is in the address
        # (the booth display connects without an id, and is not a phone)
        device = (socket.query_params.get("device") or "")[:40]
        nick = clean_name(socket.query_params.get("nick") or "", 30)
        await socket.accept()
        q: asyncio.Queue = asyncio.Queue()
        hub.clients.add(q)
        if device:
            hub.attach(device, q)
        try:
            await socket.send_text(json.dumps({"type": "hello", "data": full_state(ctx)},
                                              ensure_ascii=False, default=str))
            if device:
                try:
                    new = ctx.store.see_device(device, nick or None)
                except Exception:  # noqa: BLE001 - a greeting is not worth a broken connection
                    log.exception("recording the phone failed")
                    new = False
                # each phone has its own address on the hotspot: a new id from an address seen lately is
                # the same phone in another context (home-screen app, private window, casaN.lan)
                address = socket.client.host if socket.client else ""
                now = time.time()
                if address and now - hub.addresses.get(address, 0.0) < SAME_PHONE_S:
                    new = False
                if address:
                    hub.addresses[address] = now
                    if len(hub.addresses) > 2000:
                        hub.addresses = {a: t for a, t in hub.addresses.items() if now - t < SAME_PHONE_S}
                if new:
                    ctx.bus.publish("phone_new", device=device, nickname=nick or None)
                else:
                    ctx.bus.publish("phone_back", device=device, nickname=nick or None)

            async def pump():
                while True:
                    await socket.send_text(await q.get())

            pump_task = asyncio.create_task(pump())
            try:
                while True:
                    msg = await socket.receive_text()
                    if msg == "ping":
                        await socket.send_text('{"type":"pong"}')
            finally:
                pump_task.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.clients.discard(q)
            if device:
                hub.detach(device, q)

    @app.post("/api/welcome")
    async def welcome(body: dict, w: Who = Depends(who)):
        """The name typed on the welcome card of a new phone ({"later": true}: no name for now)."""
        if not w.device:
            raise HTTPException(400, "no phone id")
        if body.get("later"):
            ctx.bus.publish("phone_later", device=w.device)
            return {"ok": True}
        name = clean_name(str(body.get("name", "")), 30)
        if not name:
            raise HTTPException(400, "empty name")
        ctx.store.name_device(w.device, name)
        ctx.bus.publish("phone_named", device=w.device, name=name)
        return {"ok": True, "name": name}

    # ============================================================ live view
    @app.get("/api/snapshot.jpg")
    async def snapshot(overlay: int = 0):
        # the vision process makes images only while somebody watches: wait for one made after the
        # request, or the answer could be a frame from minutes ago (before the webcam was moved)
        if ctx.vision.available and not ctx.sim.enabled:
            asked = time.time()
            for _ in range(20):
                if ctx.vision.jpeg(bool(overlay), since=asked):
                    break
                await asyncio.sleep(0.1)
        return Response(_frame(ctx, bool(overlay)), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/stream")
    async def stream(fps: float = 5.0, overlay: int = 0):
        fps = max(1.0, min(fps, 10.0))

        async def gen():
            boundary = b"--frame\r\n"
            while True:
                jpg = _frame(ctx, bool(overlay))
                yield boundary + b"Content-Type: image/jpeg\r\nContent-Length: " + \
                    str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
                await asyncio.sleep(1.0 / fps)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    # ============================================================ rules
    @app.get("/api/rules")
    async def rules():
        return ctx.rules.to_list()

    @app.post("/api/rules")
    async def rule_create(body: dict, w: Who = Depends(who)):
        body = dict(body)
        body.pop("id", None)
        try:
            return ctx.rules.upsert(body, w.device, w.nickname)
        except RuleError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/api/rules/{rule_id}")
    async def rule_update(rule_id: str, body: dict, w: Who = Depends(who)):
        body = dict(body, id=rule_id)
        try:
            return ctx.rules.upsert(body, w.device, w.nickname)
        except RuleError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/rules/{rule_id}")
    async def rule_delete(rule_id: str, w: Who = Depends(who)):
        if not ctx.rules.delete(rule_id, w.device, w.nickname):
            raise HTTPException(404, "no such rule")
        return {"ok": True}

    @app.post("/api/rules/{rule_id}/enabled")
    async def rule_enable(rule_id: str, body: dict, w: Who = Depends(who)):
        r = ctx.rules.get(rule_id)
        if not r:
            raise HTTPException(404, "no such rule")
        r = dict(r, enabled=bool(body.get("enabled", True)))
        return ctx.rules.upsert(r, w.device, w.nickname)

    # ============================================================ identities
    @app.get("/api/identities")
    async def identities():
        return ctx.identities.to_list()

    @app.put("/api/identities/{identity_id}")
    async def identity_update(identity_id: str, body: dict, w: Who = Depends(who)):
        if not ctx.identities.get(identity_id):
            raise HTTPException(404, "no such identity")
        fields = {k: body[k] for k in ("name", "category", "alias_en", "facts") if k in body}
        try:
            return ctx.identities.update(identity_id, device=w.device, nickname=w.nickname,
                                         **fields).to_dict()
        except NameTaken as e:
            raise HTTPException(409, f"name taken: {e.name}") from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/identities/{identity_id}")
    async def identity_delete(identity_id: str, w: Who = Depends(who)):
        if not ctx.identities.get(identity_id):
            raise HTTPException(404, "no such identity")
        ctx.identities.delete(identity_id, device=w.device, nickname=w.nickname)
        ctx.vision.forget_identity(identity_id)
        for obj in ctx.sim.objects.values():
            if obj.identity == identity_id:
                obj.identity, obj.name = None, ""
        return {"ok": True}

    @app.post("/api/photos")
    async def photo_upload(request: Request):
        body = await request.body()
        if not body or len(body) > MAX_PHOTO or not body.startswith(b"\xff\xd8"):
            raise HTTPException(400, "send a JPEG image")
        name = new_id("ph") + ".jpg"
        (ctx.paths.photos / name).write_bytes(body)
        return {"photo": name}

    @app.get("/api/photos/{name}")
    async def photo(name: str):
        path = (ctx.paths.photos / Path(name).name)
        if not path.exists():
            raise HTTPException(404, "no such photo")
        return FileResponse(path, media_type="image/jpeg")

    # ------------------------------------------------------------ registration
    @app.post("/api/register")
    async def register_start(body: dict, w: Who = Depends(who)):
        reg = ctx.registration
        photo = body.get("photo")
        photo_path = str(ctx.paths.photos / Path(photo).name) if photo else None
        try:
            s = reg.start(body.get("name", ""), origin="web", photo=photo_path,
                          room=body.get("room"), category=body.get("category"),
                          device=w.device, nickname=w.nickname)
        except NameTaken as e:
            raise HTTPException(409, json.dumps({"error": "name_taken", "name": e.name})) from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if photo_path:
            s.photo = Path(photo_path).name
        return s.to_dict()

    @app.post("/api/register/{sid}/pick")
    async def register_pick(sid: str, body: dict):
        try:
            return ctx.registration.pick(sid, body.get("track", "")).to_dict()
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/register/{sid}/confirm")
    async def register_confirm(sid: str, body: dict):
        try:
            ident = ctx.registration.confirm(sid, body.get("category"))
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e)) from e
        except NameTaken as e:
            raise HTTPException(409, "name taken") from e
        return ident.to_dict()

    @app.delete("/api/register/{sid}")
    async def register_cancel(sid: str):
        ctx.registration.cancel(sid)
        return {"ok": True}

    # ============================================================ confirmations
    @app.post("/api/confirm/{cid}")
    async def confirm(cid: str, body: dict):
        if not ctx.house.answer(cid, body.get("value"), by="web"):
            raise HTTPException(404, "already answered")
        return {"ok": True}

    @app.post("/api/confirm/{cid}/close")
    async def close_question(cid: str):
        """Closed on a phone: the question disappears everywhere and the house stops listening for it."""
        ctx.house.withdraw(cid)
        return {"ok": True}

    @app.post("/api/alerts/{key}/dismiss")
    async def dismiss_alert(key: str):
        ctx.house.dismiss_alert(key)
        return {"ok": True}

    # ============================================================ commands
    @app.post("/api/commands/{name}")
    async def command(name: str, request: Request, w: Who = Depends(who)):
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        a = ctx.actions
        if name == "party":
            ok = await a.party()
        elif name == "grill":
            ok = await a.grill()
        elif name == "grill_stop":
            await a.grill_stop()
            ok = True
        elif name == "scene":
            ok = await a.scene(body.get("scene", "normal"))
        elif name == "light":
            await a.light(body.get("room", "all"), body.get("color", "#ffffff"),
                          body.get("effect", "solid"), int(body.get("brightness", 60)),
                          body.get("duration_s", 120))
            ok = True
        elif name == "lights_off":
            await a.lights_off(body.get("room", "all"))
            ok = True
        elif name == "lights_auto":
            await a.lights_auto(body.get("room", "all"))
            ok = True
        elif name == "language":
            ok = await a.set_language(body.get("language", "it"))
        elif name == "verbosity":
            ok = await a.set_verbosity(body.get("verbosity", "normal"))
        elif name == "volume":
            await a.set_volume(int(body.get("volume", 70)))
            ok = True
        elif name == "follow":
            ctx.settings.set("lights.follow", bool(body.get("on", True)))
            ctx.house.tick(time.time())
            ctx.bus.publish("follow", on=ctx.settings.get("lights.follow", True))
            ok = True
        elif name == "say":
            await a.say(str(body.get("text", ""))[:200])
            ok = True
        elif name == "intercom":
            if ctx.voice is None:
                raise HTTPException(503, "voice not available")
            await ctx.voice.intercom()
            ok = True
        elif name == "alarm":
            # on and off like a burglar alarm: off, the rules that raise alarms stay quiet
            on = bool(body.get("armed", True))
            ctx.house.set_armed(on, w.nickname or None)
            await a.sound("beep")
            who_it = f" da {w.nickname}" if w.nickname else ""
            who_en = f" by {w.nickname}" if w.nickname else ""
            await a.notify("info", {"it": ("Allarme inserito" if on else "Allarme disinserito") + who_it,
                                    "en": ("Alarm on" if on else "Alarm off") + who_en})
            ok = True
        else:
            raise HTTPException(404, "unknown command")
        ctx.store.add_event("command", {"name": name, "body": body, "device": w.device,
                                        "nickname": w.nickname})
        return {"ok": bool(ok)}

    # ============================================================ simulation
    @app.get("/api/sim")
    async def sim_state():
        return ctx.sim.to_dict()

    @app.post("/api/sim/enable")
    async def sim_enable(body: dict):
        ctx.sim.enabled = bool(body.get("on", True))
        ctx.sim.mute = bool(body.get("mute", False))
        ctx.house.status["simulation"] = ctx.sim.enabled
        ctx.bus.publish("sim")
        ctx.bus.publish("status", **ctx.house.status)
        return ctx.sim.to_dict()

    @app.post("/api/sim/objects")
    async def sim_add(body: dict):
        if not ctx.sim.enabled:
            raise HTTPException(409, "simulation is off")
        ident = ctx.identities.get(body.get("identity"))
        category = ident.category if ident else body.get("category", "person")
        color = ident.color if ident and ident.color != "#888888" else body.get("color", "#e03030")
        obj = ctx.sim.add(body.get("x", 300), body.get("y", 100), category,
                          ident.id if ident else None, color, ident.name if ident else "")
        ctx.bus.publish("sim")
        return obj.to_dict()

    @app.put("/api/sim/objects/{obj_id}")
    async def sim_move(obj_id: str, body: dict):
        obj = ctx.sim.move(obj_id, body.get("x", 0), body.get("y", 0))
        if not obj:
            raise HTTPException(404, "no such object")
        return obj.to_dict()

    @app.delete("/api/sim/objects/{obj_id}")
    async def sim_remove(obj_id: str):
        ctx.sim.remove(obj_id)
        ctx.bus.publish("sim")
        return {"ok": True}

    @app.post("/api/sim/sensor")
    async def sim_sensor(body: dict):
        if not ctx.sim.enabled:
            raise HTTPException(409, "simulation is off")
        for key, index in (("thermostat", 0), ("bathroom", 1)):
            if key in body:
                v = body[key]
                ctx.house.on_thermo(index, float(v.get("t", 24)), float(v.get("rh", 45)))
        return {"ok": True}

    @app.post("/api/sim/button")
    async def sim_button(body: dict):
        index = {"talk": 0, "intercom": 1, "language": 2}.get(body.get("button"), -1)
        if index < 0:
            raise HTTPException(400, "unknown button")
        if ctx.settings.get("buttons.reversed"):
            index = 2 - index
        ctx.house.on_button(index, bool(body.get("pressed", True)))
        return {"ok": True}

    # ============================================================ network sign
    @app.get("/api/sign")
    async def sign_data():
        return sign.sign_data(ctx)

    # ============================================================ settings
    @app.get("/api/settings")
    async def settings_get():
        return ctx.settings.public()

    @app.put("/api/settings")
    async def settings_put(body: dict, w: Who = Depends(who)):
        # the network has its own endpoint, which also applies it to the hotspot
        body = {k: v for k, v in body.items() if k != "network"}
        before = ctx.settings.public()
        ctx.settings.update(body)
        audit(w, "settings", None, "update", before, ctx.settings.public())
        lights = ctx.settings.get("lights")
        try:
            await ctx.mcu.limits(lights["max_brightness"], lights["current_budget_ma"])
        except Exception:  # noqa: BLE001
            pass
        if ctx.audio is not None:
            ctx.audio.set_volume(ctx.settings.get("voice.volume", 70))
        ctx.bus.publish("volume", volume=ctx.settings.get("voice.volume"))
        ctx.vision.set_privacy(ctx.settings.get("camera.blur_bathroom", True))
        return ctx.settings.public()

    @app.post("/api/network")
    async def network(body: dict, w: Who = Depends(who)):
        from .. import network as net
        password = str(body.get("password", ""))
        if not net.valid_password(password):
            raise HTTPException(400, "the Wi-Fi password must be 8 to 63 characters, letters, digits and symbols")
        try:
            exists, active = await net.hotspot_state()
            if exists:
                await net.set_hotspot_password(password)
        except net.HotspotError as e:
            raise HTTPException(503, str(e)) from e      # nothing saved: hotspot and sign stay as they were
        ctx.settings.set("network.password", password)
        audit(w, "settings", "network", "update")
        if exists and active:
            # after the answer: the phones on the hotspot drop and join again with the new password
            asyncio.get_running_loop().call_later(2.0, lambda: asyncio.ensure_future(net.restart_hotspot()))
        return {"ok": True, "applied": exists, "restarting": exists and active,
                "reason": None if exists else ("no NetworkManager on this machine" if not net.available()
                                               else "the hotspot is not set up yet: scripts/hotspot.sh setup")}

    @app.post("/api/clock")
    async def set_clock(body: dict):
        """The time set from the settings: unlike the automatic one of /api/time, it always counts."""
        if "epoch" in body:
            ok = ctx.clock.set(float(body["epoch"]), "settings")
        else:
            ok = ctx.clock.set_hm(int(body.get("hour", 0)), int(body.get("minute", 0)), "settings")
        ctx.bus.publish("clock", **ctx.clock.to_dict())
        return {"ok": ok, "clock": ctx.clock.to_dict()}

    @app.get("/api/trash")
    async def trash():
        return ctx.store.trash()

    @app.post("/api/trash/{trash_id}/restore")
    async def trash_restore(trash_id: int):
        item = ctx.store.trash_take(trash_id)
        if not item:
            raise HTTPException(404, "not in the bin")
        if item["entity"] == "rule":
            ctx.rules.upsert(item["data"])
        elif item["entity"] == "identity":
            ctx.identities.restore(item["data"])
        return {"ok": True}

    @app.post("/api/rules/defaults")
    async def rules_defaults(w: Who = Depends(who)):
        from ..default_rules import default_rules
        before = ctx.rules.to_list()
        ctx.rules.replace_all(default_rules())
        audit(w, "rule", None, "reset", before, ctx.rules.to_list())
        return ctx.rules.to_list()

    # ------------------------------------------------------------ vision (calibration, dataset)
    @app.get("/api/vision")
    async def vision_status():
        return ctx.vision.status()

    @app.post("/api/vision/{name}")
    async def vision_command(name: str, request: Request, w: Who = Depends(who)):
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        result = await asyncio.get_running_loop().run_in_executor(
            None, lambda: ctx.vision.command(name, **body))
        if name in ("corners", "empty", "adjust", "reset"):
            audit(w, "calibration", name, "update")
        return result

    @app.get("/api/vision/raw.jpg")
    async def vision_raw(overlay: int = 0):
        jpg = None
        if ctx.vision.available:
            jpg = (await asyncio.get_running_loop().run_in_executor(
                None, lambda: ctx.vision.command("raw_frame", overlay=bool(overlay)))).get("jpeg")
        return Response(jpg or _frame(ctx), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/dataset.zip")
    async def dataset_zip():
        path = ctx.vision.command("export").get("path") if ctx.vision.available else None
        if not path or not Path(path).exists():
            raise HTTPException(404, "nothing captured yet")
        return FileResponse(path, media_type="application/zip", filename="domotiq-dataset.zip")

    # ------------------------------------------------------------ diagnostics
    @app.get("/api/diagnostics")
    async def diagnostics():
        from ..diagnostics import collect
        return await collect(ctx)

    @app.post("/api/diagnostics/scan")
    async def scan():
        # the main bus (Hub, Latch Relay) answers on every channel too: each channel lists what is behind it
        out: dict[str, Any] = {}
        try:
            main = await ctx.mcu.scan(255)
            out["main"] = main
        except Exception as e:  # noqa: BLE001
            main, out["main"] = [], str(e)
        for ch in range(8):
            try:
                out[str(ch)] = [a for a in await ctx.mcu.scan(ch) if a not in main and not 0x70 <= a <= 0x77]
            except Exception as e:  # noqa: BLE001
                out[str(ch)] = str(e)
        return out

    @app.post("/api/diagnostics/sound")
    async def sound_test():
        await ctx.actions.sound("chime")
        await ctx.actions.say({"it": "Prova dell'audio: mi senti?", "en": "Audio test: can you hear me?"})
        return {"ok": ctx.audio is not None and ctx.audio.ok}

    @app.post("/api/voice/text")
    async def voice_text(body: dict):
        """A sentence handled as if it had been said with Talk (demos and tests)."""
        if ctx.voice is None:
            raise HTTPException(503, "voice not available")
        text = " ".join(str(body.get("text", "")).split())[:200]
        if not text:
            raise HTTPException(400, "empty text")
        voice = ctx.voice

        async def run() -> None:
            async with voice.busy:
                voice._talk_task = asyncio.current_task()
                await voice.handle(text)
        voice._spawn(run())
        return {"ok": True}

    @app.post("/api/diagnostics/mic")
    async def mic_test():
        if ctx.voice is None:
            raise HTTPException(503, "voice not available")
        return await ctx.voice.mic_test()

    @app.get("/api/logs")
    async def logs():
        from ..diagnostics import journal
        return Response(journal(), media_type="text/plain; charset=utf-8")

    # ------------------------------------------------------------ backup
    @app.get("/api/backup.zip")
    async def backup():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("domotiq-backup.json", json.dumps({
                "version": ctx.version, "created": time.time(),
                "rules": ctx.rules.to_list(),
                "identities": [i.to_dict() for i in ctx.identities.all()],
                "settings": {k: v for k, v in ctx.settings.public().items()
                             if k not in ("network", "house", "camera")},
            }, ensure_ascii=False, indent=2))
            for ident in ctx.identities.all():
                if ident.photo and (ctx.paths.photos / ident.photo).exists():
                    z.write(ctx.paths.photos / ident.photo, f"photos/{ident.photo}")
        house = ctx.settings.get("house.number", 1)
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="domotiq-casa{house}-backup.zip"'})

    @app.post("/api/restore")
    async def restore(request: Request, parts: str = "rules,identities,settings", w: Who = Depends(who)):
        data = await request.body()
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            doc = json.loads(z.read("domotiq-backup.json"))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
            raise HTTPException(400, "not a DomotiQ backup") from e
        wanted = set(parts.split(","))
        if "rules" in wanted:
            ctx.rules.replace_all(doc.get("rules", []))
        if "identities" in wanted:
            for name in z.namelist():
                if name.startswith("photos/"):
                    (ctx.paths.photos / Path(name).name).write_bytes(z.read(name))
            ctx.identities.replace_all(doc.get("identities", []))
        if "settings" in wanted:
            ctx.settings.update(doc.get("settings", {}))
        audit(w, "backup", None, "restore", None, {"parts": sorted(wanted)})
        return {"ok": True, "parts": sorted(wanted)}

    # ------------------------------------------------------------ system
    @app.post("/api/system/{what}")
    async def system(what: str):
        from ..diagnostics import system_action
        if what not in ("restart", "reboot", "shutdown"):
            raise HTTPException(404, "unknown")
        asyncio.get_running_loop().call_later(1.0, system_action, what)
        return {"ok": True}

    app.mount("/static", FreshStatic(directory=STATIC), name="static")
    return app


def _frame(ctx: "Context", overlay: bool = False) -> bytes:
    jpg = ctx.vision.jpeg(overlay) if ctx.vision.available and not ctx.sim.enabled else None
    if jpg:
        return jpg
    return placeholder.render(ctx)
