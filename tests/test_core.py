# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Layout, lights, climate, house events and rules, with a fake clock."""

from __future__ import annotations

import asyncio

from domotiq.climate import Shower, Thermostat
from domotiq.lights import CONSTRAINT, FOLLOW, LightRequest, parse_color
from domotiq.model import Track
from domotiq.settings import DEFAULTS


def T(tid, x, y, **kw):
    return Track(id=tid, x=x, y=y, **kw)


# ------------------------------------------------------------------ layout
def test_rooms_and_doors(layout):
    assert layout.room_at(80, 100) == "kitchen"
    assert layout.room_at(300, 100) == "living"
    assert layout.room_at(360, 300) == "utility"
    assert layout.room_at(100, -40) == "driveway"
    # in the kitchen-living doorway the previous room is kept
    assert layout.locate(170, 110, previous="kitchen") == "kitchen"
    assert layout.locate(170, 110, previous="living") == "living"
    # hysteresis: 10 mm past the kitchen wall still counts as the kitchen
    assert layout.locate(172, 110, previous="kitchen") == "kitchen"
    assert layout.locate(200, 110, previous="kitchen") == "living"
    assert layout.locate(700, 300) == "outside"


def test_excluded_zones(layout):
    assert layout.is_excluded(35, 340)            # tree canopy
    assert layout.is_excluded(160, 180)           # kitchen light
    assert not layout.is_excluded(80, 100)


# ------------------------------------------------------------------ lights
def test_light_layers(env):
    lights = env.lights
    lights.set("kitchen", "follow", LightRequest("solid", "#ffaa5a", 60, priority=FOLLOW))
    lights.set("kitchen", "alarm", LightRequest("alarm", "#ff0000", 80, priority=CONSTRAINT), duration_s=0.01)
    assert lights.resolve("kitchen").effect == "alarm"
    import time
    time.sleep(0.02)
    assert lights.resolve("kitchen").effect == "solid"
    lights.clear("kitchen", "follow")
    assert lights.resolve("kitchen").effect == "off"
    assert parse_color("red") == (255, 32, 16)


def test_refresh_sends_only_changes(env):
    env.lights.set("living", "x", LightRequest("solid", "#102030", 50))
    asyncio.run(env.lights.refresh())
    sent = [c for c in env.mcu.calls if c[0] == "light"]
    asyncio.run(env.lights.refresh())
    assert len([c for c in env.mcu.calls if c[0] == "light"]) == len(sent)
    assert any(c[1][1:5] == (1, 16, 32, 48) for c in sent)


# ------------------------------------------------------------------ climate
def test_thermostat_hot_and_back():
    cfg = dict(DEFAULTS["climate"])
    th = Thermostat(cfg)
    t = 0.0
    for _ in range(60):
        assert th.update(t, 24.0, 40.0) is None
        t += 2
    # a finger warms it by 1.2 °C
    state = None
    for i in range(20):
        state = th.update(t, 24.0 + 0.07 * i, 40.0) or state
        t += 2
    assert state == "hot"
    state = None
    for _ in range(10):
        state = th.update(t, 24.2, 40.0) or state
        t += 2
    assert state == "normal"


def test_breath_counts_as_hot():
    th = Thermostat(dict(DEFAULTS["climate"]))
    for i in range(30):
        th.update(i * 2.0, 24.0, 40.0)
    assert th.update(62, 24.1, 55.0) == "hot"


def test_shower():
    sh = Shower(dict(DEFAULTS["climate"]))
    for i in range(30):
        sh.update(i * 2.0, 50.0)
    assert sh.update(70, 60.0) == "start"
    assert sh.update(90, 52.0) == "stop"


# ------------------------------------------------------------------ house events
def test_room_events_and_counts(env):
    seen = []
    env.bus.subscribe("*", lambda e: seen.append((e.type, e.data.get("room"))))
    env.house.update_tracks([T("t1", 80, 100, category="person")], now=100)
    assert ("room_enter", "kitchen") in seen
    assert env.house.count("kitchen", "person") == 1
    env.house.update_tracks([T("t1", 300, 100, category="person")], now=101)
    assert ("room_exit", "kitchen") in seen and ("room_enter", "living") in seen
    env.house.update_tracks([], now=102)
    assert ("room_exit", "living") in seen
    assert env.house.count("living") == 0


def test_follow_lights_with_delay(env):
    env.house.update_tracks([T("t1", 80, 100, category="person")], now=100)
    assert env.lights.resolve("kitchen", now=100).source == "follow"
    env.house.update_tracks([], now=101)
    assert env.lights.resolve("kitchen", now=101).source == "follow"   # still on for 3 s
    env.house.tick(now=104.5)
    assert env.lights.resolve("kitchen", now=104.5).effect == "off"


def test_pets_do_not_switch_lights_on(env):
    env.house.update_tracks([T("d1", 80, 100, category="dog")], now=100)
    assert env.lights.resolve("kitchen", now=100).effect == "off"


def test_car_states(env):
    states = []
    env.bus.subscribe("car", lambda e: states.append(e.data["state"]))
    env.house.update_tracks([T("c1", 700, 300, category="car")], now=100)
    env.house.update_tracks([T("c1", 600, 300, category="car")], now=101)
    assert states[-1] == "arrived"
    env.house.update_tracks([T("c1", 540, 300, category="car")], now=102)
    env.house.update_tracks([T("c1", 540, 300, category="car")], now=106)
    assert states[-1] == "parked"
    env.house.update_tracks([T("c1", 700, 300, category="car")], now=110)
    assert states[-1] == "departed"
    env.house.update_tracks([T("c1", 705, 300, category="car")], now=121)
    assert states[-1] == "absent"


# ------------------------------------------------------------------ rules
def test_utility_room_grace_and_alarm(env):
    h, rules = env.house, env.rules
    h.update_tracks([T("p", 360, 300, category="person")], now=1000)
    rules.tick(now=1003)
    assert "say" not in env.executor.kinds()          # within the 5 s tolerance
    rules.tick(now=1005.5)
    assert "say" in env.executor.kinds()
    assert h.alerts, "an alert is raised"
    # leaving clears the alarm
    h.update_tracks([T("p", 300, 100, category="person")], now=1007)
    assert not h.alerts


def test_crossing_utility_to_garage_is_fine(env):
    h, rules = env.house, env.rules
    h.update_tracks([T("p", 380, 250, category="person")], now=1000)
    h.update_tracks([T("p", 500, 250, category="person")], now=1003)   # into the garage
    rules.tick(now=1010)
    assert "say" not in env.executor.kinds()


def test_bathroom_for_one(env):
    h, rules = env.house, env.rules
    h.update_tracks([T("a", 200, 300, category="person"), T("b", 220, 320, category="person")], now=1000)
    rules.tick(now=1001)
    assert "say" not in env.executor.kinds()          # 2 s grace
    rules.tick(now=1002.5)
    assert "say" in env.executor.kinds()
    assert env.lights.resolve("bathroom").effect == "blink"
    h.update_tracks([T("a", 200, 300, category="person")], now=1004)
    assert not h.alerts
    asyncio.run(env.lights.refresh())
    assert env.lights.resolve("bathroom").effect != "blink"


def test_pets_do_not_count_in_bathroom(env):
    h, rules = env.house, env.rules
    h.update_tracks([T("a", 200, 300, category="person"), T("d", 220, 320, category="dog")], now=1000)
    rules.tick(now=1005)
    assert "say" not in env.executor.kinds()


def test_rule_crud_and_audit(env):
    r = env.rules.upsert({"name": "Test", "when": {"type": "button", "button": "talk"},
                          "then": [{"type": "sound", "name": "chime"}]}, device="dev1", nickname="Ema")
    assert env.rules.get(r["id"])
    env.rules.delete(r["id"], device="dev1")
    assert not env.rules.get(r["id"])
    audit = env.store.audit()
    assert audit[0]["action"] == "delete" and audit[1]["nickname"] == "Ema"
    assert env.store.trash()[0]["entity_id"] == r["id"]


def test_invalid_rule_rejected(env):
    import pytest
    from domotiq.rules import RuleError
    with pytest.raises(RuleError):
        env.rules.upsert({"name": "x", "when": {"type": "nope"}, "then": [{"type": "say"}]})
    with pytest.raises(RuleError):
        env.rules.upsert({"name": "x", "when": {"type": "button"}, "then": []})


def test_placeholders(env):
    from domotiq.activities import Actions

    class Ctx:
        settings = env.settings
        layout = env.layout
    a = Actions(Ctx())
    assert a.fill({"it": "{name} è in {room}"}, {"name": "Marco", "room": "kitchen"}, "it") == "Marco è in Cucina"
    assert a.fill({"en": "{count} people"}, {"count": 2}, "en") == "2 people"


def test_intruder_rule_only_while_away(env):
    from domotiq.default_rules import default_rules
    env.rules.replace_all(default_rules())
    env.house.update_tracks([T("t1", 300, 100, category="person")], 1000.0)
    assert "say" not in env.executor.kinds()
    env.house.update_tracks([], 1001.0)
    env.house.set_scene("away")
    env.house.update_tracks([T("t2", 80, 100, category="person")], 1002.0)
    assert any(c[0] == "say" and "Intruso" in c[1] for c in env.executor.calls)
