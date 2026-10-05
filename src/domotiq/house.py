# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The state of the house, and the events that describe how it changes.

Tracks arrive from the vision pipeline (or from the simulation) as the full
list of what is visible now. The house compares it with the previous list
and turns the differences into events: someone entered a room, a room got
crowded, the car parked. Rules, lights, voice and web app all listen to
those events instead of looking at the tracks themselves.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .bus import Bus
from .climate import Shower, Thermostat
from .identities import Identities
from .layout import OUTSIDE, Layout
from .lights import FOLLOW, NAMED_COLORS, SCENE, LightController, LightRequest
from .model import ANIMALS, CAR, OBJECT, PERSON, Track, category_matches, new_id
from .scenes import SCENES
from .settings import Settings
from .store import Store

BUTTONS = ("talk", "intercom", "language")
MOVE_MM = 6.0
NAMED_S = 3.0      # a name somebody gave stays on its presence this long, while the vision (another process) catches up


@dataclass
class CarState:
    track: str
    identity: str | None
    room: str | None = None
    state: str = "absent"            # arrived | parked | departed | absent
    last_x: float = 0.0
    last_y: float = 0.0
    still_since: float = field(default_factory=time.time)
    left_garage_at: float | None = None
    parked_at: float | None = None


class House:
    def __init__(self, layout: Layout, bus: Bus, identities: Identities,
                 lights: LightController, settings: Settings, store: Store) -> None:
        self.layout = layout
        self.bus = bus
        self.identities = identities
        self.lights = lights
        self.settings = settings
        self.store = store

        self.tracks: dict[str, Track] = {}
        self.counts: dict[str, dict[str, int]] = {r: _empty_count() for r in layout.rooms}
        self.sensors: dict[str, dict[str, Any]] = {
            "thermostat": {"t": None, "rh": None, "ts": 0.0},
            "bathroom": {"t": None, "rh": None, "ts": 0.0},
        }
        self.scene = "normal"
        self.grill_on = False
        self.party_on = False
        self.climate = "normal"
        self.shower = False
        self.cars: dict[str, CarState] = {}
        self.alerts: dict[str, dict[str, Any]] = {}
        self.confirmations: dict[str, dict[str, Any]] = {}
        self.dismissed_alerts: set[str] = set()
        self.status = {"mcu": False, "camera": False, "audio": False, "llm": False,
                       "simulation": False, "modules": {}}
        self._follow_off_at: dict[str, float] = {}
        self._dropped: dict[str, float] = {}     # presences said not real: until when they are left out
        self._named: dict[str, tuple[str, float]] = {}   # presence -> (name somebody just gave it, until when)
        self._last_sample = 0.0
        self._now: float | None = None

        climate_cfg = settings.get("climate")
        self.thermostat = Thermostat(climate_cfg)
        self.bathroom_humidity = Shower(climate_cfg)

    def _pub(self, event_type: str, **data: Any) -> None:
        self.bus.publish(event_type, _ts=self._now, **data)

    # ================================================================ tracks
    def update_tracks(self, tracks: list[Track], now: float | None = None) -> None:
        now = now or time.time()
        self._now = now
        self._dropped = {k: until for k, until in self._dropped.items() if until > now}
        self._named = {k: v for k, v in self._named.items() if v[1] > now}
        named = {tid: ident for tid, (ident, _) in self._named.items()}
        moved = set(named.values())
        new: dict[str, Track] = {}
        for t in tracks:
            if t.id in self._dropped:
                continue                       # said not real: the vision has not dropped it yet
            prev = self.tracks.get(t.id)
            t.room = self.layout.locate(t.x, t.y, prev.room if prev else None)
            # the names come from the vision; one somebody has just given is kept until the vision has it too, and
            # meanwhile it is nowhere else
            if t.id in named:
                if t.identity == named[t.id]:
                    self._named.pop(t.id, None)
                t.identity, t.uncertain, t.candidates = named[t.id], False, []
            elif t.identity in moved:
                t.identity, t.uncertain, t.candidates = None, False, []
            if t.identity:
                ident = self.identities.get(t.identity)
                if ident:
                    t.category = ident.category
                    t.color = ident.color if t.color == "#888888" else t.color
            new[t.id] = t
        # a name is never in two places: if two presences come with the same one, the one in sight keeps it
        holder: dict[str, Track] = {}
        for t in sorted(new.values(), key=lambda t: (t.carried, t.hidden, t.uncertain, -t.confidence)):
            if not t.identity:
                continue
            if t.identity in holder:
                t.identity, t.uncertain, t.candidates = None, False, []
            else:
                holder[t.identity] = t

        for tid, prev in self.tracks.items():
            if tid not in new:
                self._emit_room("room_exit", prev, prev.room, None)
                self._pub("track_disappear", **self._who(prev), room=prev.room)
                if prev.identity and not any(n.identity == prev.identity for n in new.values()):
                    self._pub("identity_disappear", **self._who(prev), room=prev.room)

        for tid, t in new.items():
            prev = self.tracks.get(tid)
            if prev is None:
                self._pub("track_appear", **self._who(t), room=t.room)
                if t.identity and not any(o.identity == t.identity for o in self.tracks.values()):
                    self._pub("identity_appear", **self._who(t), room=t.room)
                self._emit_room("room_enter", t, t.room, None)
                continue
            if prev.identity != t.identity:
                self._pub("identity_changed", **self._who(t), before=prev.identity)
                if t.identity:
                    self._pub("identity_appear", **self._who(t), room=t.room)
            if prev.room != t.room:
                self._emit_room("room_exit", prev, prev.room, t.room)
                self._emit_room("room_enter", t, t.room, prev.room)
            if prev.on != t.on and not t.carried:
                self._pub("furniture", **self._who(t), room=t.room, on=t.on, before=prev.on)

        self.tracks = new
        # a "who is it?" the house has meanwhile answered by itself (only one of the names could be there, or it
        # recognized the newcomer) is withdrawn, on the phones and aloud
        for cid, c in list(self.confirmations.items()):
            t = new.get(c["context"].get("track")) if c["context"].get("kind") == "who" else None
            if t is not None and t.identity and not t.uncertain:
                self.withdraw(cid)
        self._update_counts()
        self._update_cars(now)
        self._update_follow(now)
        if now - self._last_sample >= 1.0:
            self._last_sample = now
            self.store.add_positions([(now, t.id, t.identity, t.x, t.y, t.room)
                                      for t in new.values() if not t.carried])
        self._pub("tracks_changed", tracks=[t.to_dict() for t in new.values()])

    def name(self, track: Track, identity: str, category: str | None = None) -> str | None:
        """Somebody said who this presence is (web app, voice, doorbell): the house shows it at once, the name leaves
        wherever else it was, and stays here while the vision catches up. Returns the name it had before."""
        for other in self.tracks.values():
            if other is not track and other.identity == identity:
                other.identity, other.uncertain, other.candidates = None, False, []
        before = track.identity
        track.identity, track.uncertain, track.candidates = identity, False, []
        if category:
            track.category = category
        # the latest name given wins: one given a moment ago to another presence is not kept there any more
        self._named = {k: v for k, v in self._named.items() if v[0] != identity}
        self._named[track.id] = (identity, (self._now or time.time()) + NAMED_S)
        return before

    def drop_track(self, track_id: str, now: float | None = None) -> None:
        """A presence somebody said is not real leaves the house now (rooms, counts, lights, questions), and is
        left out for a few seconds, until the vision has forgotten it too."""
        now = now or time.time()
        self._dropped[track_id] = now + 5.0
        self.update_tracks([t for t in self.tracks.values() if t.id != track_id], now)

    def _who(self, t: Track) -> dict[str, Any]:
        return {"track": t.id, "identity": t.identity, "category": t.category,
                "name": self.identities.name_of(t.identity), "sure": t.sure}

    def _emit_room(self, kind: str, t: Track, room: str | None, other: str | None) -> None:
        if not room:
            return
        data = self._who(t)
        data["room"] = room
        data["other"] = other
        self._pub(kind, **data)

    def _update_counts(self) -> None:
        counts = {r: _empty_count() for r in self.layout.rooms}
        counts[OUTSIDE] = _empty_count()
        for t in self.tracks.values():
            c = counts.setdefault(t.room or OUTSIDE, _empty_count())
            c[_group(t.category)] += 1
            c["total"] += 1
            c["sure"] += int(t.sure)           # alarms count only these: a change wakes them up
        # in place before the change is told: the web app sends the phones self.counts as soon as it hears it,
        # and the old counts would keep every page one change behind
        before, self.counts = self.counts, counts
        for room, c in counts.items():
            if c != before.get(room):
                self._pub("count_changed", room=room, **c)

    def count(self, room: str | None = None, category: str | None = None, sure: bool = False) -> int:
        """How many tracks of a category (or group) are in a room, or in the whole house; with `sure`, only those
        sure enough for an alarm."""
        n = 0
        for t in self.tracks.values():
            if sure and not t.sure:
                continue
            if room and room != "house" and t.room != room:
                continue
            if room == "house" and (t.room == OUTSIDE or t.room == "driveway"):
                continue
            if category_matches(t.category, category):
                n += 1
        return n

    def where_is(self, identity: str) -> Track | None:
        return next((t for t in self.tracks.values() if t.identity == identity), None)

    def in_room(self, room: str, category: str | None = None) -> list[Track]:
        return [t for t in self.tracks.values() if t.room == room and category_matches(t.category, category)]

    # ================================================================ cars
    def _update_cars(self, now: float) -> None:
        cfg = self.settings.get("garage")
        seen = set()
        for t in self.tracks.values():
            if t.category != CAR:
                continue
            seen.add(t.id)
            car = self.cars.get(t.id)
            if car is None:
                car = self.cars[t.id] = CarState(t.id, t.identity, t.room, last_x=t.x, last_y=t.y,
                                                 state="parked" if t.room == "garage" else "absent")
                if t.room == "garage":
                    car.parked_at = now
            moved = abs(t.x - car.last_x) + abs(t.y - car.last_y) > MOVE_MM
            if moved:
                car.still_since = now
                car.last_x, car.last_y = t.x, t.y
            in_garage = t.room == "garage"
            if in_garage and car.room != "garage":
                self._car_event(car, "arrived")
                car.left_garage_at = None
                car.parked_at = None
            elif not in_garage and car.room == "garage":
                self._car_event(car, "departed")
                car.left_garage_at = now
                car.parked_at = None
            if (in_garage and car.state != "parked" and self.layout.in_parking(t.x, t.y)
                    and now - car.still_since >= cfg["parked_after_s"]):
                self._car_event(car, "parked")
                car.parked_at = now
            if (not in_garage and car.state == "departed" and car.left_garage_at
                    and now - car.left_garage_at >= cfg["absent_after_s"]):
                self._car_event(car, "absent")
            car.room = t.room
            car.identity = t.identity
        for tid in [k for k in self.cars if k not in seen]:
            car = self.cars.pop(tid)
            if car.state in ("arrived", "parked") and car.room == "garage":
                # hidden by a hand while parked: it has not left, keep quiet
                continue
            if car.state != "absent":
                self._car_event(car, "absent")

    def _car_event(self, car: CarState, state: str) -> None:
        car.state = state
        self._pub("car", state=state, track=car.track, identity=car.identity,
                         name=self.identities.name_of(car.identity))

    def car_state(self) -> str:
        """The state of the first car the house knows about."""
        for car in self.cars.values():
            return car.state
        return "absent"

    # ================================================================ lights
    def _update_follow(self, now: float) -> None:
        cfg = self.settings.get("lights")
        scene = SCENES.get(self.scene, SCENES["normal"])
        follow = cfg.get("follow", True) and scene.get("follow", True)
        color = scene.get("follow_color", cfg["follow_color"])
        brightness = scene.get("follow_brightness", cfg["follow_brightness"])
        gcfg = self.settings.get("garage")
        favourite = cfg.get("follow_favourite", True) and "follow_color" not in scene
        for lid, light in self.layout.lights.items():
            wanted = follow and self.count(light.room, PERSON) > 0
            if follow and light.room == "garage":
                for car in self.cars.values():
                    if car.room != "garage":
                        continue
                    if car.state != "parked" or (car.parked_at and now - car.parked_at < gcfg["light_off_after_s"]):
                        wanted = True
            if wanted:
                self._follow_off_at.pop(lid, None)
                c = (self._favourite_in(light.room) if favourite else None) or color
                self.lights.set(lid, "follow", LightRequest("solid", c, brightness, priority=FOLLOW))
            elif "follow" in self.lights.layers[lid]:
                off_at = self._follow_off_at.setdefault(lid, now + cfg["follow_off_delay_s"])
                if now >= off_at or not follow:
                    self.lights.clear(lid, "follow")
                    self._follow_off_at.pop(lid, None)

    def _favourite_in(self, room: str) -> str | None:
        """The favourite colour of the person who came into this room last, among those who told the house theirs."""
        from .voice.facts import favourite_colour
        people = sorted((t for t in self.tracks.values()
                         if t.room == room and t.identity and not t.uncertain and category_matches(t.category, PERSON)),
                        key=lambda t: t.since, reverse=True)
        for t in people:
            ident = self.identities.get(t.identity)
            colour = favourite_colour(ident.facts) if ident is not None else None
            if colour in NAMED_COLORS:
                return NAMED_COLORS[colour]
        return None

    def set_scene(self, scene: str) -> bool:
        if scene not in SCENES:
            return False
        self.scene = scene
        self.lights.clear_prefix("scene")
        for room, req in SCENES[scene].get("rooms", {}).items():
            self.lights.set(room, "scene", LightRequest(req.get("effect", "solid"), req["color"],
                                                        req.get("brightness", 40), priority=SCENE))
        self._update_follow(time.time())
        self._pub("scene", scene=scene)
        return True

    def tick(self, now: float | None = None) -> None:
        """Called a few times per second: timers that do not need new tracks."""
        now = now or time.time()
        self._now = now
        self._update_follow(now)
        self._update_cars(now)

    # ================================================================ sensors
    def on_thermo(self, index: int, temp: float, rh: float, now: float | None = None) -> None:
        now = now or time.time()
        self._now = now
        key = "thermostat" if index == 0 else "bathroom"
        self.sensors[key] = {"t": round(temp, 2), "rh": round(rh, 1), "ts": now}
        self._pub("sensor", sensor=key, t=temp, rh=rh)
        if key == "thermostat":
            state = self.thermostat.update(now, temp, rh)
            if state:
                self.climate = state
                self._pub("climate", state=state, t=temp, rh=rh)
        else:
            state = self.bathroom_humidity.update(now, rh)
            if state:
                self.shower = state == "start"
                self._pub("shower", state=state, rh=rh)

    def on_button(self, index: int, pressed: bool) -> None:
        self._now = None
        if self.settings.get("buttons.reversed"):
            index = 2 - index
        if 0 <= index < len(BUTTONS):
            self._pub("button", button=BUTTONS[index], pressed=bool(pressed))

    # ================================================================ alarm
    @property
    def armed(self) -> bool:
        """The alarm is on: the rules that raise alarms work. Off, like a burglar alarm switched off, they stay
        quiet (everything else goes on as usual)."""
        return bool(self.settings.get("alarm.armed", True))

    def set_armed(self, on: bool, by: str | None = None) -> None:
        self.settings.set("alarm.armed", bool(on))
        self._now = None
        self._pub("armed", armed=bool(on), by=by)

    # ================================================================ alerts, confirmations
    def set_alert(self, key: str, **data: Any) -> None:
        if key in self.dismissed_alerts:
            return                      # closed on a phone: not again until what caused it is over
        fresh = key not in self.alerts
        self.alerts[key] = {"key": key, "since": self.alerts.get(key, {}).get("since", time.time()), **data}
        if fresh:
            self._pub("alerts_changed", alerts=list(self.alerts.values()))

    def clear_alert(self, key: str) -> None:
        self.dismissed_alerts.discard(key)
        if self.alerts.pop(key, None) is not None:
            self._pub("alerts_changed", alerts=list(self.alerts.values()))

    def dismiss_alert(self, key: str) -> bool:
        """Closed on a phone: it disappears everywhere, and comes back only once it has ended and happens
        again."""
        self.dismissed_alerts.add(key)
        if self.alerts.pop(key, None) is None:
            return False
        self._pub("alerts_changed", alerts=list(self.alerts.values()))
        return True

    def ask(self, question: dict[str, str], options: list[dict[str, Any]],
            context: dict[str, Any] | None = None, timeout_s: float = 60.0, allow_name: bool = False) -> str:
        """A question to the visitors, aloud and on the phones: the first answer wins, from either. With
        `allow_name` the answer may also be a new name ({"name": ...})."""
        cid = new_id("ask")
        self.confirmations[cid] = {"id": cid, "question": question, "options": options,
                                   "context": context or {}, "expires": time.time() + timeout_s,
                                   "allow_name": allow_name}
        self._pub("confirm", **self.confirmations[cid])
        return cid

    def answer(self, cid: str, value: Any, by: str = "web") -> bool:
        item = self.confirmations.pop(cid, None)
        if not item:
            return False
        self._pub("confirm_answer", id=cid, value=value, by=by, context=item["context"])
        self._pub("confirm_closed", id=cid)
        return True

    def withdraw(self, cid: str) -> bool:
        """The question no longer makes sense (what it was about has gone): it disappears everywhere."""
        item = self.confirmations.pop(cid, None)
        if not item:
            return False
        self._pub("confirm_answer", id=cid, value=None, by="gone", context=item["context"])
        self._pub("confirm_closed", id=cid)
        return True

    def expire_confirmations(self, now: float | None = None) -> None:
        now = now or time.time()
        for cid, item in list(self.confirmations.items()):
            if item["expires"] <= now:
                self.confirmations.pop(cid, None)
                self._pub("confirm_answer", id=cid, value=None, by="timeout",
                                 context=item["context"])
                self._pub("confirm_closed", id=cid)

    # ================================================================ snapshot
    def snapshot(self) -> dict[str, Any]:
        return {
            "tracks": [t.to_dict() for t in self.tracks.values()],
            "counts": self.counts,
            "sensors": self.sensors,
            "scene": self.scene,
            "grill": self.grill_on,
            "party": self.party_on,
            "climate": self.climate,
            "shower": self.shower,
            "cars": {k: v.state for k, v in self.cars.items()},
            "car": self.car_state(),
            "alerts": list(self.alerts.values()),
            # of the context the phones only need what a "who is it?" is about
            "confirmations": [{**{k: v for k, v in c.items() if k != "context"},
                               "who": c["context"].get("kind") == "who" and c.get("allow_name", False),
                               "category": c["context"].get("category")}
                              for c in self.confirmations.values()],
            "lights": self.lights.state(),
            "status": self.status,
            "language": self.settings.get("voice.language"),
            "verbosity": self.settings.get("voice.verbosity"),
            "armed": self.armed,
        }


def _empty_count() -> dict[str, int]:
    return {"persons": 0, "animals": 0, "cars": 0, "objects": 0, "total": 0, "sure": 0}


def _group(category: str | None) -> str:
    if category == PERSON:
        return "persons"
    if category in ANIMALS:
        return "animals"
    if category == CAR:
        return "cars"
    return "objects" if category == OBJECT or category is None else "objects"
