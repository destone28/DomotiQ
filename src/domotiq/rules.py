# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""When / If / Then rules.

A rule has one trigger ("when"), any number of conditions that must all be
true ("if"), and a list of actions ("then"). Rules are plain JSON so the web
app can edit them and anyone can read them. Timers (someone staying in a
room, a room staying crowded, a visitor standing at the doorbell) are kept
here and advanced by `tick()`, so tests can drive them with a fake clock.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from .bus import Bus, Event
from .house import House
from .lights import CONSTRAINT, RULE, LightController, LightRequest
from .model import category_matches, new_id
from .settings import Paths, read_json, write_json_atomic
from .store import Store

log = logging.getLogger(__name__)

TRIGGERS = ("enter_room", "exit_room", "dwell", "count_above", "count_below",
            "identity_appear", "identity_disappear", "time", "sensor_above", "sensor_below",
            "climate", "shower", "button", "visitor", "car", "scene", "grill", "party")
CONDITIONS = ("room_occupied", "room_empty", "count", "identity_present", "identity_absent",
              "time_between", "sensor", "scene_is", "grill_is", "car_is", "climate_is")
ACTIONS = ("light", "light_off", "sound", "say", "relay", "notify", "scene", "party",
           "grill", "wait")


# triggers that end by themselves (leaving the room, the count going back): their alarms last until then
HELD = ("dwell", "count_above", "count_below")
ALERT_HOLD_S = 30.0


class Executor(Protocol):
    """What rules can make the house do, besides lights."""

    async def say(self, text: dict[str, str], ctx: dict[str, Any]) -> None: ...
    async def sound(self, name: str) -> None: ...
    async def relay(self, on: bool, duration_s: float | None) -> None: ...
    async def notify(self, level: str, text: dict[str, str], ctx: dict[str, Any]) -> None: ...
    async def scene(self, scene: str) -> None: ...
    async def party(self) -> None: ...
    async def grill(self) -> None: ...


class RuleError(ValueError):
    pass


def validate(rule: dict[str, Any]) -> dict[str, Any]:
    """Check a rule coming from the web app and fill in the defaults."""
    if not isinstance(rule, dict):
        raise RuleError("a rule is an object")
    r = copy.deepcopy(rule)
    r.setdefault("id", new_id("r"))
    name = r.get("name") or {}
    if isinstance(name, str):
        name = {"it": name, "en": name}
    if not (name.get("it") or name.get("en")):
        raise RuleError("the rule needs a name")
    r["name"] = {"it": name.get("it") or name.get("en"), "en": name.get("en") or name.get("it")}
    r["enabled"] = bool(r.get("enabled", True))
    r["priority"] = int(max(1, min(98, int(r.get("priority", RULE)))))
    r["cooldown_s"] = float(max(0, float(r.get("cooldown_s", 5))))
    r["alert"] = bool(r.get("alert", False))
    when = r.get("when") or {}
    if when.get("type") not in TRIGGERS:
        raise RuleError(f"unknown trigger {when.get('type')!r}")
    r["when"] = when
    r["if"] = list(r.get("if") or [])
    for c in r["if"]:
        if c.get("type") not in CONDITIONS:
            raise RuleError(f"unknown condition {c.get('type')!r}")
    r["then"] = list(r.get("then") or [])
    if not r["then"]:
        raise RuleError("the rule does nothing: add at least one action")
    for a in r["then"]:
        if a.get("type") not in ACTIONS:
            raise RuleError(f"unknown action {a.get('type')!r}")
    return r


@dataclass
class Timer:
    rule: str
    key: str
    fire_at: float
    ctx: dict[str, Any]


def _who_ok(who: dict[str, Any] | None, data: dict[str, Any]) -> bool:
    if not who:
        return True
    if who.get("identity") and who["identity"] != data.get("identity"):
        return False
    if data.get("identity") and data["identity"] in (who.get("except") or []):
        return False
    return category_matches(data.get("category"), who.get("category"))


def _cmp(value: float, op: str, target: float) -> bool:
    return {">": value > target, ">=": value >= target, "<": value < target,
            "<=": value <= target, "=": value == target, "==": value == target,
            "!=": value != target}.get(op, False)


class RuleEngine:
    def __init__(self, paths: Paths, bus: Bus, house: House, lights: LightController,
                 store: Store, executor: Executor | None = None) -> None:
        self.path = paths.config / "rules.json"
        self.bus = bus
        self.house = house
        self.lights = lights
        self.store = store
        self.executor = executor
        saved = read_json(self.path, None)
        if saved is None:
            from .default_rules import default_rules
            saved = default_rules()
            write_json_atomic(self.path, saved)
        self.rules: list[dict[str, Any]] = []
        for r in saved:
            try:
                self.rules.append(validate(r))
            except RuleError as e:
                log.warning("rule %s skipped: %s", r.get("id"), e)
        self.last_fired: dict[str, float] = {}
        self.timers: dict[str, Timer] = {}
        self.latched: dict[str, bool] = {}
        self.alert_keys: dict[str, str] = {}      # timer key -> alert key
        self.alert_until: dict[str, float] = {}   # alerts of one-off events end by themselves
        self._minute = ""
        self._tasks: set[asyncio.Task] = set()
        for t in ("room_enter", "room_exit", "track_disappear", "count_changed", "identity_appear",
                  "identity_disappear", "sensor", "climate", "shower", "button", "distance",
                  "car", "scene", "grill", "party"):
            bus.subscribe(t, self.on_event)

    # ================================================================ storage
    def save(self) -> None:
        write_json_atomic(self.path, self.rules)

    def get(self, rule_id: str) -> dict[str, Any] | None:
        return next((r for r in self.rules if r["id"] == rule_id), None)

    def upsert(self, rule: dict[str, Any], device: str | None = None,
               nickname: str | None = None) -> dict[str, Any]:
        r = validate(rule)
        before = self.get(r["id"])
        if before:
            self.rules[self.rules.index(before)] = r
        else:
            self.rules.append(r)
        self._forget(r["id"])
        self.save()
        self.store.add_audit("rule", r["id"], "update" if before else "create", before, r,
                             device, nickname)
        self.bus.publish("rules_changed", rule=r["id"])
        return r

    def delete(self, rule_id: str, device: str | None = None, nickname: str | None = None) -> bool:
        r = self.get(rule_id)
        if not r:
            return False
        self.rules.remove(r)
        self._forget(rule_id)
        self.save()
        self.store.trash_put("rule", rule_id, r, device, nickname)
        self.store.add_audit("rule", rule_id, "delete", r, None, device, nickname)
        self.bus.publish("rules_changed", rule=rule_id)
        return True

    def replace_all(self, rules: list[dict[str, Any]]) -> None:
        self.rules = [validate(r) for r in rules]
        for rid in list(self.last_fired):
            self._forget(rid)
        self.save()
        self.bus.publish("rules_changed", rule=None)

    def _forget(self, rule_id: str) -> None:
        for key in [k for k, t in self.timers.items() if t.rule == rule_id]:
            self.timers.pop(key, None)
        for key in [k for k in self.latched if k.startswith(rule_id + "|")]:
            self.latched.pop(key, None)
        self.lights.clear_prefix(f"rule:{rule_id}")
        for tkey, akey in list(self.alert_keys.items()):
            if tkey.startswith(rule_id + "|"):
                self.house.clear_alert(akey)
                self.alert_keys.pop(tkey, None)

    # ================================================================ events
    def on_event(self, ev: Event, now: float | None = None) -> None:
        now = now or ev.ts or time.time()
        for rule in self.rules:
            if not rule["enabled"]:
                continue
            try:
                self._match(rule, ev, now)
            except Exception:  # noqa: BLE001
                log.exception("rule %s failed on %s", rule["id"], ev.type)

    def _room_ok(self, wanted: str | None, room: str | None) -> bool:
        """A room of the rule: one room, "any" room, or "indoor" (every room inside the house)."""
        if wanted in (None, "any"):
            return True
        if wanted == "indoor":
            return room in self.house.layout.indoor_rooms()
        return wanted == room

    def _match(self, rule: dict[str, Any], ev: Event, now: float) -> None:
        w = rule["when"]
        t = w["type"]
        d = ev.data
        if t == "enter_room" and ev.type == "room_enter":
            if self._room_ok(w.get("room"), d.get("room")) and _who_ok(w.get("who"), d):
                self.fire(rule, dict(d), now)
        elif t == "exit_room" and ev.type == "room_exit":
            if self._room_ok(w.get("room"), d.get("room")) and _who_ok(w.get("who"), d):
                self.fire(rule, dict(d), now)
        elif t == "dwell":
            key = f"{rule['id']}|{d.get('track')}"
            if ev.type == "room_enter" and d.get("room") == w.get("room") and _who_ok(w.get("who"), d):
                self.timers[key] = Timer(rule["id"], key, now + float(w.get("seconds", 5)), dict(d))
            elif ev.type in ("room_exit", "track_disappear") and d.get("room") == w.get("room"):
                self.timers.pop(key, None)
                self._release(key)
        elif t in ("count_above", "count_below") and ev.type == "count_changed":
            if d.get("room") != w.get("room"):
                return
            key = f"{rule['id']}|{w.get('room')}"
            n = self.house.count(w.get("room"), (w.get("who") or {}).get("category"))
            value = float(w.get("value", 0))
            active = n > value if t == "count_above" else n < value
            if active and not self.latched.get(key) and key not in self.timers:
                ctx = {"room": w.get("room"), "count": n}
                self.timers[key] = Timer(rule["id"], key, now + float(w.get("grace_s", 0)), ctx)
            elif not active:
                self.timers.pop(key, None)
                self.latched.pop(key, None)
                self._release(key)
        elif t == "identity_appear" and ev.type == "identity_appear":
            if _who_ok(w.get("who"), d):
                self.fire(rule, dict(d), now)
        elif t == "identity_disappear" and ev.type == "identity_disappear":
            if _who_ok(w.get("who"), d):
                self.fire(rule, dict(d), now)
        elif t in ("sensor_above", "sensor_below") and ev.type == "sensor":
            if d.get("sensor") != w.get("sensor", "thermostat"):
                return
            q = w.get("quantity", "t")
            value = d.get(q)
            if value is None:
                return
            key = f"{rule['id']}|sensor"
            target = float(w.get("value", 0))
            hyst = 0.3 if q == "t" else 2.0
            crossed = value > target if t == "sensor_above" else value < target
            cleared = value < target - hyst if t == "sensor_above" else value > target + hyst
            if crossed and not self.latched.get(key):
                self.latched[key] = True
                self.fire(rule, {"temp": d.get("t"), "rh": d.get("rh"), "sensor": d.get("sensor")}, now)
            elif cleared:
                self.latched.pop(key, None)
        elif t == "climate" and ev.type == "climate":
            if w.get("state") in (None, d.get("state")):
                self.fire(rule, {"temp": d.get("t"), "rh": d.get("rh"), "state": d.get("state")}, now)
        elif t == "shower" and ev.type == "shower":
            if w.get("state", "start") == d.get("state"):
                self.fire(rule, {"rh": d.get("rh"), "state": d.get("state")}, now)
        elif t == "button" and ev.type == "button":
            if d.get("pressed") and w.get("button") in (None, d.get("button")):
                self.fire(rule, dict(d), now)
        elif t == "visitor" and ev.type == "distance":
            key = f"{rule['id']}|visitor"
            mm = d.get("mm")
            near = mm is not None and mm < float(w.get("distance_cm", 30)) * 10
            if near and not self.latched.get(key) and key not in self.timers:
                self.timers[key] = Timer(rule["id"], key, now + float(w.get("seconds", 2)), {"mm": mm})
            elif not near:
                self.timers.pop(key, None)
                self.latched.pop(key, None)
        elif t == "car" and ev.type == "car":
            if w.get("state") in (None, d.get("state")):
                self.fire(rule, dict(d), now)
        elif t == "scene" and ev.type == "scene":
            if w.get("scene") in (None, d.get("scene")):
                self.fire(rule, dict(d), now)
        elif t in ("grill", "party") and ev.type == t:
            if w.get("state") in (None, d.get("state")):
                self.fire(rule, dict(d), now)

    # ================================================================ time
    def tick(self, now: float | None = None) -> None:
        now = now or time.time()
        for key, until in list(self.alert_until.items()):
            if until <= now:
                self.alert_until.pop(key, None)
                self._release(key)
        for key, timer in list(self.timers.items()):
            if timer.fire_at > now:
                continue
            self.timers.pop(key, None)
            rule = self.get(timer.rule)
            if not rule or not rule["enabled"]:
                continue
            w = rule["when"]
            if w["type"] == "dwell":
                track = self.house.tracks.get(timer.ctx.get("track"))
                if not track or track.room != w.get("room"):
                    self._release(key)
                    continue
            if w["type"] in ("count_above", "count_below"):
                n = self.house.count(w.get("room"), (w.get("who") or {}).get("category"))
                value = float(w.get("value", 0))
                if not (n > value if w["type"] == "count_above" else n < value):
                    continue
                timer.ctx["count"] = n
                self.latched[key] = True
            if w["type"] == "visitor":
                self.latched[key] = True
            self.fire(rule, timer.ctx, now, key=key, bypass_cooldown=True)
            repeat = float(w.get("repeat_s", 0) or 0)
            if repeat > 0 and w["type"] in ("dwell", "count_above"):
                self.timers[key] = Timer(rule["id"], key, now + repeat, timer.ctx)
        minute = datetime.fromtimestamp(now).strftime("%H:%M")
        if minute != self._minute:
            self._minute = minute
            for rule in self.rules:
                if rule["enabled"] and rule["when"]["type"] == "time" and rule["when"].get("at") == minute:
                    self.fire(rule, {"time": minute}, now)

    def _release(self, key: str) -> None:
        akey = self.alert_keys.pop(key, None)
        if akey:
            self.house.clear_alert(akey)
            rule_id = key.split("|")[0]
            self.lights.clear_prefix(f"rule:{rule_id}:{key}")

    # ================================================================ firing
    def conditions_ok(self, rule: dict[str, Any], now: float) -> bool:
        for c in rule["if"]:
            if not self._condition(c, now):
                return False
        return True

    def _condition(self, c: dict[str, Any], now: float) -> bool:
        t = c["type"]
        h = self.house
        cat = (c.get("who") or {}).get("category")
        if t == "room_occupied":
            return h.count(c.get("room"), cat) > 0
        if t == "room_empty":
            return h.count(c.get("room"), cat) == 0
        if t == "count":
            return _cmp(h.count(c.get("room"), cat), c.get("op", ">"), float(c.get("value", 0)))
        if t == "identity_present":
            return h.where_is(c.get("identity")) is not None
        if t == "identity_absent":
            return h.where_is(c.get("identity")) is None
        if t == "time_between":
            now_hm = datetime.fromtimestamp(now).strftime("%H:%M")
            a, b = c.get("from", "00:00"), c.get("to", "23:59")
            return a <= now_hm <= b if a <= b else (now_hm >= a or now_hm <= b)
        if t == "sensor":
            value = h.sensors.get(c.get("sensor", "thermostat"), {}).get(c.get("quantity", "t"))
            return value is not None and _cmp(value, c.get("op", ">"), float(c.get("value", 0)))
        if t == "scene_is":
            return h.scene == c.get("scene")
        if t == "grill_is":
            return h.grill_on == bool(c.get("on", True))
        if t == "car_is":
            return h.car_state() == c.get("state")
        if t == "climate_is":
            return h.climate == c.get("state")
        return False

    def fire(self, rule: dict[str, Any], ctx: dict[str, Any], now: float,
             key: str | None = None, bypass_cooldown: bool = False) -> bool:
        if not bypass_cooldown and now - self.last_fired.get(rule["id"], 0) < rule["cooldown_s"]:
            return False
        if not self.conditions_ok(rule, now):
            return False
        self.last_fired[rule["id"]] = now
        key = key or f"{rule['id']}|{ctx.get('track') or 'event'}"
        if rule["alert"]:
            akey = f"{rule['id']}:{ctx.get('track') or ctx.get('room') or 'x'}"
            self.alert_keys[key] = akey
            if rule["when"]["type"] not in HELD:
                # nothing will say when a one-off event is over: the alarm lasts as long as its lights
                self.alert_until[key] = now + ALERT_HOLD_S
            self.house.set_alert(akey, rule=rule["id"], name=rule["name"], room=ctx.get("room"),
                                 who=ctx.get("name") or None)
        self.bus.publish("rule_fired", rule=rule["id"], name=rule["name"], ctx=_plain(ctx))
        self.store.add_event("rule", {"rule": rule["id"], "name": rule["name"], "ctx": _plain(ctx)},
                             "warning" if rule["alert"] else "info")
        self._spawn(self._run(rule, ctx, key))
        return True

    def _spawn(self, coro) -> None:
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            # no loop (unit tests without asyncio): run the synchronous part now
            try:
                asyncio.run(coro)
            except Exception:  # noqa: BLE001
                log.exception("rule actions failed")
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, rule: dict[str, Any], ctx: dict[str, Any], key: str) -> None:
        ex = self.executor
        for a in rule["then"]:
            t = a["type"]
            try:
                if t == "light":
                    layer = f"rule:{rule['id']}:{key}" if rule["alert"] else f"rule:{rule['id']}"
                    prio = CONSTRAINT if rule["alert"] else rule["priority"]
                    duration = a.get("duration_s")
                    if duration is None and not rule["alert"]:
                        duration = 30
                    self.lights.set(a.get("room", "all"), layer,
                                    LightRequest(a.get("effect", "solid"), a.get("color", "#ffffff"),
                                                 int(a.get("brightness", 60)), int(a.get("speed", 50)),
                                                 priority=prio),
                                    duration_s=float(duration) if duration else None)
                    await self.lights.refresh()
                elif t == "light_off":
                    self.lights.clear_prefix(f"rule:{a.get('rule') or rule['id']}")
                    await self.lights.refresh()
                elif t == "wait":
                    await asyncio.sleep(min(float(a.get("seconds", 1)), 600))
                elif ex is None:
                    continue
                elif t == "sound":
                    await ex.sound(a.get("name", "chime"))
                elif t == "say":
                    await ex.say(a.get("text") or {}, {**ctx, "_verbosity": a.get("verbosity", "normal")})
                elif t == "relay":
                    await ex.relay(bool(a.get("on", True)), a.get("duration_s"))
                elif t == "notify":
                    await ex.notify(a.get("level", "info"), a.get("text") or {}, ctx)
                elif t == "scene":
                    await ex.scene(a.get("scene", "normal"))
                elif t == "party":
                    await ex.party()
                elif t == "grill":
                    await ex.grill()
            except Exception:  # noqa: BLE001 - one failing action does not stop the others
                log.exception("action %s of rule %s failed", t, rule["id"])

    def to_list(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.rules)


def _plain(ctx: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in ctx.items() if isinstance(v, (str, int, float, bool, type(None)))}
