# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Layout, lights, climate, house events and rules, with a fake clock."""

from __future__ import annotations

import time
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


def test_a_name_is_never_in_two_places_in_the_house(env):
    h = env.house
    ross = env.identities.add("Rossellina", "person")
    # the vision recognized Rossellina in the kitchen, then moved the name to the one in the living room
    h.update_tracks([T("a", 80, 100, identity=ross.id), T("b", 300, 100)], now=100)
    h.update_tracks([T("a", 80, 100), T("b", 300, 100, identity=ross.id)], now=101)
    assert {t.id: t.identity for t in h.tracks.values()} == {"a": None, "b": ross.id}
    # two presences coming with the same name (one of them in a hand): the one in sight keeps it
    h.update_tracks([T("a", 80, 100, identity=ross.id, carried=True), T("b", 300, 100, identity=ross.id)], now=102)
    assert {t.id: t.identity for t in h.tracks.values()} == {"a": None, "b": ross.id}


def test_a_name_given_in_the_web_app_waits_for_the_vision(env):
    h = env.house
    ross = env.identities.add("Rossellina", "person")
    h.update_tracks([T("a", 80, 100, identity=ross.id), T("b", 300, 100)], now=100)
    assert h.name(h.tracks["b"], ross.id) is None
    # the vision (another process) still sends the old picture: the name stays where it was given, and only there
    h.update_tracks([T("a", 80, 100, identity=ross.id), T("b", 300, 100)], now=100.5)
    assert {t.id: t.identity for t in h.tracks.values()} == {"a": None, "b": ross.id}
    h.update_tracks([T("a", 80, 100), T("b", 300, 100, identity=ross.id)], now=101)     # now the vision has it
    # and from then on the names are the vision's
    h.update_tracks([T("a", 80, 100), T("b", 300, 100)], now=101.5)
    assert h.tracks["b"].identity is None
    # given to one, then at once to the other: the latest wins, even before the vision has either
    h.name(h.tracks["a"], ross.id)
    h.name(h.tracks["b"], ross.id)
    h.update_tracks([T("a", 80, 100), T("b", 300, 100)], now=102)
    assert {t.id: t.identity for t in h.tracks.values()} == {"a": None, "b": ross.id}


def test_follow_lights_with_delay(env):
    env.house.settings.set("lights.follow", True)          # off by default for now
    env.house.update_tracks([T("t1", 80, 100, category="person")], now=100)
    assert env.lights.resolve("kitchen", now=100).source == "follow"
    env.house.update_tracks([], now=101)
    assert env.lights.resolve("kitchen", now=101).source == "follow"   # still on for 3 s
    env.house.tick(now=104.5)
    assert env.lights.resolve("kitchen", now=104.5).effect == "off"


def test_at_a_start_the_lights_wait_for_the_vision(env):
    """12 October: lit for the first figurine found at a start, a light of its favourite colour cast a glow that looked
    like other characters while the vision was still looking."""
    env.house.settings.set("lights.follow", True)
    env.house.follow_after_start()
    env.house.update_tracks([T("t1", 80, 100, category="person")], now=100)
    assert env.lights.resolve("kitchen", now=100).effect == "off"
    env.house.update_tracks([T("t1", 80, 100, category="person")], now=110)
    assert env.lights.resolve("kitchen", now=110).effect == "off"
    env.house.update_tracks([T("t1", 80, 100, category="person")], now=115.5)
    assert env.lights.resolve("kitchen", now=115.5).source == "follow"


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


def test_alarms_wait_until_the_house_is_sure(env):
    h, rules = env.house, env.rules
    # something just born in the utility room, not yet sure: no alarm, however long the rule waits
    h.update_tracks([T("p", 360, 300, category="person", sure=False)], now=1000)
    rules.tick(now=1005.5)
    rules.tick(now=1008)
    assert "say" not in env.executor.kinds() and not h.alerts
    # still there and now sure: the alarm comes at the next look
    h.update_tracks([T("p", 360, 300, category="person", sure=True)], now=1008.5)
    rules.tick(now=1009.5)
    assert "say" in env.executor.kinds() and h.alerts


def test_two_in_the_bathroom_only_if_both_are_sure(env):
    h, rules = env.house, env.rules
    h.update_tracks([T("a", 200, 300, category="person"), T("b", 220, 320, category="person", sure=False)], now=1000)
    rules.tick(now=1003)
    assert "say" not in env.executor.kinds()
    h.update_tracks([T("a", 200, 300, category="person"), T("b", 220, 320, category="person", sure=True)], now=1004)
    rules.tick(now=1006.5)
    assert "say" in env.executor.kinds()


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


def test_a_saved_rule_with_an_unknown_trigger_is_skipped(env):
    import json
    from domotiq.rules import RuleEngine
    saved = [r for r in env.rules.to_list()] + [{
        "id": "r-old", "name": {"it": "Regola vecchia", "en": "Old rule"},
        "enabled": True, "when": {"type": "no_such_trigger"},
        "then": [{"type": "sound", "name": "chime"}]}]
    env.rules.path.write_text(json.dumps(saved))
    rules = RuleEngine(env.paths, env.bus, env.house, env.lights, env.store, env.executor)
    ids = [r["id"] for r in rules.to_list()]
    assert "r-old" not in ids and len(ids) == len(saved) - 1          # the others are all there


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


def test_every_scene_looks_different_with_nobody_home(env):
    """Normal, cinema, relax, night and away: before, with no figurine in the house, four of them were all dark."""
    def lit():
        return {k: (v["effect"], v["color"]) for k, v in env.lights.state().items() if v["effect"] != "off"}
    looks = {}
    for scene in ("normal", "cinema", "relax", "night"):
        env.house.set_scene(scene)
        env.house.tick(1000.0)
        looks[scene] = lit()
    assert looks["normal"] == {}                                    # the lights follow people
    assert looks["cinema"] == {"living": ("sparkle", "#3a5cff")}    # the glow of a screen
    assert looks["relax"]["living"][0] == "fire" and looks["relax"]["bedroom"][0] == "breathe"
    assert looks["night"] == {"bathroom": ("solid", "#ff7a30")}     # a night light
    # away: one room at a time lights up, as if somebody were in, then another one
    env.house.set_scene("away")
    env.house.tick(2000.0)
    first = lit()
    assert len(first) == 1 and next(iter(first)) in ("kitchen", "living", "bedroom", "bathroom")
    env.house.tick(2000.0 + 31.0)
    second = lit()
    assert len(second) == 1 and second != first
    env.house.set_scene("normal")                                   # nothing of it is left
    env.house.tick(2100.0)
    assert lit() == {}


def test_alarm_of_a_one_off_event_ends_by_itself(env):
    rule = {"id": "r-x", "name": {"it": "x", "en": "x"}, "alert": True,
            "when": {"type": "enter_room", "room": "kitchen"},
            "then": [{"type": "light", "room": "kitchen", "effect": "alarm", "color": "#ff0000"}]}
    env.rules.upsert(rule)
    env.house.update_tracks([T("t1", 80, 100, category="person")], 1000.0)
    assert env.house.alerts
    env.rules.tick(1010.0)
    assert env.house.alerts
    env.rules.tick(1031.0)
    assert not env.house.alerts


def test_sound_card_choice_and_levels(tmp_path):
    from domotiq.audio.output import find_card, mixer_commands
    # the webcam enumerated first: it has a microphone only, the house must take the US205
    (tmp_path / "cards").write_text(
        " 0 [WEBCAM         ]: USB-Audio - C270 HD WEBCAM\n"
        "                      C270 HD WEBCAM at usb-xhci-hcd.2.auto-1.2, high speed\n"
        " 1 [Device         ]: USB-Audio - USB Audio Device\n"
        "                      C-Media Electronics Inc. USB Audio Device at usb-xhci-hcd.2.auto-1.1\n")
    for index, pcms in (("0", ["pcm0c"]), ("1", ["pcm0c", "pcm0p"])):
        (tmp_path / f"card{index}").mkdir()
        for pcm in pcms:
            (tmp_path / f"card{index}" / pcm).mkdir()
    assert find_card(tmp_path) == "plughw:CARD=Device,DEV=0"
    (tmp_path / "card1" / "pcm0p").rmdir()
    assert find_card(tmp_path) is None

    us205 = """Simple mixer control 'Speaker',0
  Capabilities: pvolume pswitch pswitch-joined
  Playback channels: Front Left - Front Right
  Limits: Playback 0 - 37
  Front Left: Playback 14 [38%] [-23.00dB] [on]
Simple mixer control 'Mic',0
  Capabilities: pvolume pvolume-joined cvolume cvolume-joined pswitch pswitch-joined cswitch cswitch-joined
  Mono: Playback 16 [52%] [-7.00dB] [off] Capture 35 [100%] [23.00dB] [on]
Simple mixer control 'Auto Gain Control',0
  Capabilities: pswitch pswitch-joined
  Mono: Playback [on]
"""
    assert mixer_commands(us205, 80) == [["Speaker,0", "playback", "100%", "unmute"],
                                         ["Mic,0", "playback", "0%", "mute"],
                                         ["Mic,0", "capture", "80%", "cap"]]


US205_OK = """Simple mixer control 'Speaker',0
  Capabilities: pvolume pswitch pswitch-joined
  Playback channels: Front Left - Front Right
  Limits: Playback 0 - 37
  Mono:
  Front Left: Playback 37 [100%] [0.00dB] [on]
  Front Right: Playback 37 [100%] [0.00dB] [on]
Simple mixer control 'Mic',0
  Capabilities: pvolume pvolume-joined cvolume cvolume-joined pswitch pswitch-joined cswitch cswitch-joined
  Playback channels: Mono
  Capture channels: Mono
  Limits: Playback 0 - 31 Capture 0 - 35
  Mono: Playback 0 [0%] [-99999.99dB] [off] Capture 35 [100%] [23.00dB] [on]
Simple mixer control 'Auto Gain Control',0
  Capabilities: pswitch pswitch-joined
  Playback channels: Mono
  Mono: Playback [on]
"""


def test_the_levels_of_the_card_are_recognised():
    """10 October: amixer of the US205 as the house leaves it, and what may change it."""
    from domotiq.audio.output import levels_ok
    assert levels_ok(US205_OK, 100)
    assert not levels_ok(US205_OK.replace("Playback 37 [100%] [0.00dB] [on]", "Playback 14 [38%] [-23.00dB] [on]", 1))
    assert not levels_ok(US205_OK.replace("[0.00dB] [on]", "[0.00dB] [off]", 1))          # the speakers muted
    assert not levels_ok(US205_OK.replace("Playback 0 [0%] [-99999.99dB] [off]", "Playback 16 [52%] [-7.00dB] [on]"))
    assert levels_ok(US205_OK.replace("Playback 0 [0%] [-99999.99dB] [off]", "Playback 16 [52%] [-7.00dB] [off]"))
    assert not levels_ok(US205_OK, 80) and levels_ok(US205_OK.replace("Capture 35 [100%]", "Capture 28 [80%]"), 80)


def test_levels_changed_by_somebody_else_are_set_again(monkeypatch):
    """The stream took sound and nothing was heard: the levels are read back and set again, off the mixer thread."""
    import subprocess

    from domotiq.audio import output
    calls = []
    contents = {"now": US205_OK.replace("Playback 37 [100%] [0.00dB] [on]", "Playback 14 [38%] [-23.00dB] [on]")}
    monkeypatch.setattr(output.subprocess, "run",
                        lambda args, **kw: subprocess.CompletedProcess(args, 0, stdout=contents["now"], stderr=""))
    monkeypatch.setattr(output, "set_hardware_levels", lambda device, gain=100: calls.append((device, gain)) or True)
    audio = output.Audio(type("S", (), {"get": lambda self, k, d=None: d})(), device="plughw:CARD=Device,DEV=0")
    audio._check_levels()
    assert calls == [("plughw:CARD=Device,DEV=0", 100)] and audio.levels_fixed == 1
    contents["now"] = US205_OK
    audio._check_levels()
    assert len(calls) == 1 and audio.status()["levels_fixed"] == 1


def test_the_stream_is_opened_again_when_the_webcam_is_opened():
    """10 October: the webcam reset on the same USB hub just after the stream was opened, and the sound card went on
    taking sound without playing it. Once the webcam is open the stream is closed, and the loop opens it again."""
    import subprocess

    from domotiq.audio.output import Audio
    audio = Audio(type("S", (), {"get": lambda self, k, d=None: d})(), device="plughw:CARD=X,DEV=0")
    assert not audio._take_reopen()                               # nothing asked
    proc = subprocess.Popen(["sleep", "5"], stdin=subprocess.PIPE)
    audio._proc = proc
    audio.reopen("the webcam was opened")
    assert audio._take_reopen() and audio._proc is None and proc.poll() is not None
    assert not audio._take_reopen() and audio.restarts == 0       # no error: asked


def test_phone_sets_the_clock_only_when_unknown():
    from domotiq.clock import HouseClock
    c = HouseClock(can_set=False)
    c.source = "unknown"
    assert c.set(time.time() + 3600, "phone") and c.source == "phone"
    assert not c.set(time.time() - 3600, "phone")          # a second phone with another time: ignored
    assert c.set(time.time() + 120, "settings") and c.source == "settings"


def test_the_time_set_holds_until_the_board_stops(tmp_path, monkeypatch):
    """After an update the application starts again and asked "Non so che ore sono": the board had not stopped."""
    from domotiq import clock as clock_mod
    monkeypatch.setattr(clock_mod.HouseClock, "ntp_synced", staticmethod(lambda: False))
    boot = tmp_path / "boot_id"
    boot.write_text("boot-1\n")
    monkeypatch.setattr(clock_mod, "BOOT_ID", boot)
    state = tmp_path / "clock.json"
    c = clock_mod.HouseClock(can_set=False, state=state)
    assert not c.known
    assert c.set(time.time() + 3, "phone")
    assert clock_mod.HouseClock(can_set=False, state=state).known          # the application started again
    boot.write_text("boot-2\n")                                          # the board started again: ask
    assert not clock_mod.HouseClock(can_set=False, state=state).known


# ------------------------------------------------------------------ a sound card that resets by itself
def test_a_reset_of_the_sound_card_is_noticed(tmp_path):
    from domotiq.audio.output import card_identity
    root = tmp_path / "asound"
    (root / "card0").mkdir(parents=True)
    (root / "cards").write_text(" 0 [Device         ]: USB-Audio - USB Audio Device\n")
    (root / "card0" / "usbbus").write_text("001/009\n")
    assert card_identity("plughw:CARD=Device,DEV=0", root) == "001/009"
    (root / "card0" / "usbbus").write_text("001/010\n")          # it came back as a new USB device
    assert card_identity("plughw:CARD=Device,DEV=0", root) == "001/010"
    (root / "cards").write_text("")                             # gone
    assert card_identity("plughw:CARD=Device,DEV=0", root) is None


def test_a_stream_that_takes_no_sound_is_started_again():
    import os
    import subprocess

    from domotiq.audio.output import STALL_S, Audio
    audio = Audio(type("S", (), {"get": lambda self, k, d=None: d})(), device="plughw:CARD=X,DEV=0")
    import fcntl

    from domotiq.audio.output import F_SETPIPE_SZ
    proc = subprocess.Popen(["sleep", "5"], stdin=subprocess.PIPE)   # alive, but never reads: stuck
    fcntl.fcntl(proc.stdin.fileno(), F_SETPIPE_SZ, 4096)            # as the house opens it
    os.set_blocking(proc.stdin.fileno(), False)
    audio._proc, audio._taken = proc, 0.0
    now = 0.0
    while audio._proc is not None and now < 5:
        audio._write(b"\0" * 882, now)
        now += 0.02
    assert audio._proc is None and audio.restarts == 1 and STALL_S <= now < STALL_S + 0.5
    assert proc.poll() is not None                              # the stuck aplay was stopped


def test_with_no_sound_card_the_sentences_still_end():
    import asyncio

    import numpy as np

    from domotiq.audio.output import Audio
    audio = Audio(type("S", (), {"get": lambda self, k, d=None: d})(), device="plughw:CARD=Gone,DEV=0")
    audio._open = lambda: False                                 # the card is not there
    audio.start()

    async def say():
        await asyncio.wait_for(audio.play_voice(np.zeros(2205, np.float32)), 2.0)   # a tenth of a second
    try:
        asyncio.run(say())
    finally:
        audio.stop()


def test_sentences_are_kept_on_disk_and_read_back_after_a_restart(tmp_path, monkeypatch):
    import io
    import os
    import wave
    from domotiq.voice import tts
    calls = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout=20):
        import json as _json
        calls.append(_json.loads(req.data)["text"])
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\x10\x00" * 2205)
        return Answer(out.getvalue())
    monkeypatch.setattr(tts.urllib.request, "urlopen", urlopen)

    async def scenario():
        first = tts.Speaker(cache_dir=tmp_path / "voice")
        a = await first.synth("Chi è?", "it")
        assert calls == ["Chi è?"] and len(list((tmp_path / "voice").glob("*.wav"))) == 1
        again = tts.Speaker(cache_dir=tmp_path / "voice")           # the house started again
        b = await again.synth("Chi è?", "it")
        assert calls == ["Chi è?"] and b is not None and len(a) == len(b)
        # the frequent sentences: the ones on disk are read back, only the new one goes to Piper
        calls.clear()
        third = tts.Speaker(cache_dir=tmp_path / "voice")
        await third.warm({"it": ["Chi è?", "Vediamo..."]})
        assert calls == ["Vediamo..."] and third.ok and len(third.cache) == 2
        # too many on disk: the ones not said for the longest time go
        files = sorted((tmp_path / "voice").glob("*.wav"))
        os.utime(files[0], (1, 1))
        third.disk_max = 1
        third._prune()
        assert sorted((tmp_path / "voice").glob("*.wav")) == files[1:]
    asyncio.run(scenario())


def test_phrases_are_given_to_piper_as_phonemes():
    from domotiq.voice import tts
    assert "[[" in tts.normalize("Come si chiama?", "it")

def test_sentences_prepared_ahead_of_time_are_read_from_their_folder(tmp_path):
    import io
    import wave
    from domotiq.voice import tts
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x10\x00" * 2205)
    seed = tmp_path / "voice-cache"
    seed.mkdir()
    (seed / tts.Speaker._name("it", "Chi è?")).write_bytes(out.getvalue())
    sp = tts.Speaker(url="http://127.0.0.1:9/none", cache_dir=tmp_path / "voice", seed_dir=seed)

    async def scenario():
        assert await sp.synth("Chi è?", "it") is not None          # from the folder prepared ahead of time
        assert await sp.synth("Vediamo...", "it") is None         # not there, and no Piper to ask
    asyncio.run(scenario())
    import importlib.util
    spec = importlib.util.spec_from_file_location("voice_cache", "scripts/voice_cache.py")
    vc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vc)
    said = vc.sentences()
    assert ("it", "Chi è?") in said and ("en", "Who is it?") in said and ("it", "Dimmi!") in said
    assert not any("{" in t or "|" in t for _, t in said) and len(said) > 150
