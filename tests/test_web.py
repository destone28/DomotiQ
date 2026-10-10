# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The web API, on a simulated house."""

from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from domotiq.app import build, parse_args  # noqa: E402
from domotiq.web.server import create_app  # noqa: E402


@pytest.fixture
def web(tmp_path):
    ctx = build(parse_args(["--simulate", "--var", str(tmp_path / "var"), "--no-audio", "--no-camera"]))
    client = TestClient(create_app(ctx), headers={"X-Device": "test-phone", "X-Nickname": "Tester"})
    yield ctx, client
    ctx.store.close()


def settle(ctx):
    """What the periodic loop does: the virtual figurines reach the house."""
    ctx.house.update_tracks(ctx.sim.tracks(), time.time())
    ctx.registration.poll()


def test_pages_and_state(web):
    ctx, c = web
    assert c.get("/").status_code == 200
    st = c.get("/api/state").json()
    for key in ("tracks", "lights", "rules", "identities", "layout"):
        assert key in st, key
    jpg = c.get("/api/snapshot.jpg")
    assert jpg.status_code == 200 and jpg.content[:2] == b"\xff\xd8"
    assert c.get("/manifest.webmanifest").json()["short_name"] == "DomotiQ"


def test_rules_crud_with_audit(web):
    ctx, c = web
    rule = {
        "name": {"it": "Prova", "en": "Test"},
        "when": {"type": "enter_room", "room": "kitchen", "who": {"category": "person"}},
        "if": [],
        "then": [{"type": "say", "text": {"it": "Ciao", "en": "Hi"}}],
    }
    r = c.post("/api/rules", json=rule)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert any(x["id"] == rid for x in c.get("/api/rules").json())
    assert c.post(f"/api/rules/{rid}/enabled", json={"enabled": False}).json()["enabled"] is False
    assert c.delete(f"/api/rules/{rid}").json()["ok"]
    assert c.delete(f"/api/rules/{rid}").status_code == 404
    log = c.get("/api/audit").json()
    assert {e["action"] for e in log if e["entity"] == "rule"} >= {"create", "update", "delete"}
    assert all(e["nickname"] == "Tester" for e in log if e["entity"] == "rule")
    bad = dict(rule, then=[{"type": "nonsense"}])
    assert c.post("/api/rules", json=bad).status_code == 400


def test_the_rules_off_at_the_start_are_switched_on_from_the_list(web):
    """The switch of the list was a box of no size outside a label: a tap never reached it, and the rules that start
    off (the party, the grill in company) could not be switched on."""
    ctx, c = web
    for rid in ("r-crowded-party", "r-crowded-garden"):
        assert c.post(f"/api/rules/{rid}/enabled", json={"enabled": True}).json()["enabled"] is True
        assert next(r for r in c.get("/api/rules").json() if r["id"] == rid)["enabled"] is True
    box = c.get("/static/css/app.css").text.split(".switch input {")[1].split("}")[0]
    assert "inset: 0" in box and "width: 0" not in box                 # the box covers the switch, in a label or not


def test_registration_with_a_virtual_figurine(web):
    ctx, c = web
    obj = c.post("/api/sim/objects", json={"x": 300, "y": 100, "category": "person", "color": "#20a0e0"}).json()
    settle(ctx)
    s = c.post("/api/register", json={"name": "Marco"}).json()
    assert s["status"] == "confirm" and s["track"] == obj["id"]
    ident = c.post(f"/api/register/{s['id']}/confirm", json={"category": "person"}).json()
    assert ident["name"] == "Marco"
    assert c.post("/api/register", json={"name": "marco"}).status_code == 409   # names are unique
    settle(ctx)
    tracks = c.get("/api/state").json()["tracks"]
    assert tracks[0]["identity"] == ident["id"] and tracks[0]["room"] == "living"
    # rename and delete, with the bin
    assert c.put(f"/api/identities/{ident['id']}", json={"name": "Marco Polo"}).json()["name"] == "Marco Polo"
    assert c.delete(f"/api/identities/{ident['id']}").status_code == 200
    assert c.get("/api/identities").json() == []


def test_two_candidates_are_offered(web):
    ctx, c = web
    c.post("/api/sim/objects", json={"x": 300, "y": 100})
    c.post("/api/sim/objects", json={"x": 520, "y": 150})
    settle(ctx)
    s = c.post("/api/register", json={"name": "Sofia"}).json()
    assert s["status"] == "choose" and len(s["candidates"]) == 2
    s = c.post(f"/api/register/{s['id']}/pick", json={"track": s["candidates"][1]}).json()
    assert s["status"] == "confirm"


def test_settings_and_tools_are_open_to_everybody(web):
    ctx, c = web
    ctx.settings._data["old"] = {"pin": "0000"}       # a section an older version left in the file
    settings = c.get("/api/settings").json()
    assert "voice" in settings and "old" not in settings
    assert c.put("/api/settings", json={"voice": {"question_every_s": 90}}).status_code == 200
    assert ctx.settings.get("voice.question_every_s") == 90
    assert "mcu" in c.get("/api/diagnostics").json()
    assert c.get("/api/backup.zip").content[:2] == b"PK"


def test_commands_and_confirmations(web):
    ctx, c = web
    assert c.post("/api/commands/scene", json={"scene": "relax"}).status_code == 200
    assert ctx.house.scene == "relax"
    cid = ctx.house.ask({"it": "Chi è?", "en": "Who is it?"},
                        [{"value": "a", "label": {"it": "A", "en": "A"}}], {"kind": "test"})
    assert c.post(f"/api/confirm/{cid}", json={"value": "a"}).json()["ok"]
    assert c.post(f"/api/confirm/{cid}", json={"value": "a"}).status_code == 404
    assert c.post("/api/commands/nonsense", json={}).status_code in (400, 404)


def test_websocket_hello(web):
    ctx, c = web
    with c.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and "tracks" in hello["data"]
        ws.send_text("ping")
        assert ws.receive_json()["type"] in ("pong", "status", "sim", "tracks")


def test_the_phones_get_the_new_counts_at_once(web):
    """Somebody enters, moves or leaves: the phones get the counts after the change, not those from before
    (the House page would stay one change behind until reloaded)."""
    import asyncio
    import json
    ctx, c = web
    phone = asyncio.Queue()
    c.app.state.hub.clients.add(phone)

    def last_counts():
        msgs = [json.loads(phone.get_nowait()) for _ in range(phone.qsize())]
        return [m["data"] for m in msgs if m["type"] == "counts"][-1]

    obj = c.post("/api/sim/objects", json={"x": 300, "y": 100, "category": "person"}).json()
    settle(ctx)
    assert last_counts()["living"]["persons"] == 1
    c.put(f"/api/sim/objects/{obj['id']}", json={"x": 90, "y": 100})
    settle(ctx)
    counts = last_counts()
    assert counts["kitchen"]["persons"] == 1 and counts["living"]["persons"] == 0
    c.delete(f"/api/sim/objects/{obj['id']}")
    settle(ctx)
    assert last_counts()["kitchen"]["persons"] == 0


def test_the_wifi_password_is_changed_from_the_settings(web):
    ctx, c = web
    assert c.post("/api/network", json={"password": "short"}).status_code == 400
    assert c.post("/api/network", json={"password": "x" * 64}).status_code == 400
    r = c.post("/api/network", json={"password": "casa-nuova-2026"}).json()
    assert r["ok"] and not r["applied"] and r["reason"]     # no NetworkManager on a test machine: saved only
    assert ctx.settings.get("network.password") == "casa-nuova-2026"
    # the generic settings endpoint cannot change the network behind the hotspot's back
    c.put("/api/settings", json={"network": {"password": "sneaky-pass"}})
    assert ctx.settings.get("network.password") == "casa-nuova-2026"


def test_admin_command_line(tmp_path):
    from domotiq.admin import main
    from domotiq.settings import Paths, Settings
    var = str(tmp_path / "var")
    assert main(["--var", var, "wifi", "short"]) == 2
    assert main(["--var", var, "wifi", "una-password-lunga"]) == 0
    s = Settings(Paths(var))
    assert s.get("network.password") == "una-password-lunga"


def test_an_alarm_closed_on_a_phone_stays_closed_until_it_happens_again(web):
    ctx, c = web
    h = ctx.house
    h.set_alert("r-utility", name={"it": "Locale tecnico riservato", "en": "Utility room reserved"})
    assert [a["key"] for a in c.get("/api/state").json()["alerts"]] == ["r-utility"]
    assert c.post("/api/alerts/r-utility/dismiss").json()["ok"]
    assert c.get("/api/state").json()["alerts"] == []
    h.set_alert("r-utility", name={"it": "Locale tecnico riservato", "en": "Utility room reserved"})
    assert c.get("/api/state").json()["alerts"] == []        # still the same alarm: it stays closed
    h.clear_alert("r-utility")                                # over
    h.set_alert("r-utility", name={"it": "Locale tecnico riservato", "en": "Utility room reserved"})
    assert len(c.get("/api/state").json()["alerts"]) == 1     # it happens again: shown again


def test_the_pages_load_their_files_under_a_version_and_questions_close(web):
    ctx, c = web
    html = c.get("/").text
    assert '"/static/v' in html and '"/static/js/' not in html          # a new version, new addresses
    path = html.split('src="')[1].split('"')[0]                          # the script of the page
    r = c.get(path)
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert c.get("/static/v1/../server.py").status_code == 404
    assert c.get("/static/js/app.js").headers["cache-control"] == "no-cache"
    cid = ctx.house.ask({"it": "Chi è?", "en": "Who is it?"}, [], {"kind": "who", "track": "t-x"})
    assert c.post(f"/api/confirm/{cid}/close").json()["ok"]
    assert not ctx.house.confirmations


def test_the_alarm_is_switched_off_and_on_like_a_burglar_alarm(web):
    ctx, c = web
    from domotiq.model import Track
    h = ctx.house
    h.update_tracks([Track("p", 360, 300, category="person")], now=1000)
    ctx.rules.tick(now=1006)
    assert h.alerts                                      # somebody in the utility room: the alarm goes off
    assert c.post("/api/commands/alarm", json={"armed": False}).json()["ok"]
    assert not h.alerts and c.get("/api/state").json()["armed"] is False
    ctx.rules.tick(now=1030)
    assert not h.alerts                                  # off: quiet, however long they stay
    assert c.post("/api/commands/alarm", json={"armed": True}).json()["ok"]
    assert c.get("/api/state").json()["brief"]["armed"] is True
    ctx.rules.tick(now=time.time() + 6)
    assert h.alerts                                      # on again: whoever is still there is noticed


def test_a_presence_seen_by_mistake_is_removed_from_a_phone(web):
    ctx, c = web
    ctx.sim.enabled = True
    obj = c.post("/api/sim/objects", json={"x": 300, "y": 100, "category": "person", "color": "#d03030"}).json()
    settle(ctx)
    assert obj["id"] in ctx.house.tracks and ctx.house.counts["living"]["persons"] == 1
    assert c.post(f"/api/tracks/{obj['id']}/dismiss").json()["ok"]
    assert obj["id"] not in ctx.house.tracks and ctx.house.counts["living"]["persons"] == 0
    settle(ctx)
    assert obj["id"] not in ctx.house.tracks                # gone for good, not back at the next update
    assert c.post("/api/tracks/nothing/dismiss").status_code == 404


def test_a_presence_the_vision_still_sends_stays_out_for_a_moment(web):
    ctx, c = web
    from domotiq.model import Track
    h = ctx.house
    h.update_tracks([Track("t1", 300, 100, category="person")], now=1000)
    h.drop_track("t1", now=1000.5)
    h.update_tracks([Track("t1", 300, 100, category="person")], now=1001)    # sent before the vision forgot it
    assert "t1" not in h.tracks
    h.update_tracks([Track("t1", 300, 100, category="person")], now=1010)    # long after: a real presence again
    assert "t1" in h.tracks


def test_a_presence_is_named_from_a_phone_new_or_known(web):
    """Who a presence is, chosen on a phone: a new name, or one the house knows (the name moves there from wherever
    it was: never in two places). A new name already used is refused, with who has it."""
    ctx, c = web
    ctx.sim.enabled = True
    a = c.post("/api/sim/objects", json={"x": 300, "y": 100, "category": "object", "color": "#d03030"}).json()
    b = c.post("/api/sim/objects", json={"x": 80, "y": 100, "category": "person", "color": "#20a0e0"}).json()
    settle(ctx)
    r = c.post(f"/api/tracks/{a['id']}/identity", json={"name": "Rosaria", "category": "person"}).json()
    rosaria = ctx.identities.by_name("Rosaria")
    assert r["ok"] and rosaria is not None and rosaria.category == "person"
    assert ctx.house.tracks[a["id"]].identity == rosaria.id
    r = c.post(f"/api/tracks/{b['id']}/identity", json={"name": "rosaria"})
    assert r.status_code == 409 and r.json()["identity"] == rosaria.id
    # the other one was Rosaria after all: the name moves
    assert c.post(f"/api/tracks/{b['id']}/identity", json={"identity": rosaria.id}).json()["ok"]
    settle(ctx)
    assert ctx.house.tracks[b["id"]].identity == rosaria.id and ctx.house.tracks[a["id"]].identity is None
    assert c.post("/api/tracks/nothing/identity", json={"identity": rosaria.id}).status_code == 404


def test_a_question_answered_with_any_known_character(web):
    ctx, c = web
    from domotiq.app import _wire
    _wire(ctx)                                  # the answers of the questions reach the vision
    ctx.sim.enabled = True
    viola = ctx.identities.add("Viola", "person")
    a = c.post("/api/sim/objects", json={"x": 300, "y": 100, "category": "person", "color": "#d03030"}).json()
    settle(ctx)
    cid = ctx.house.ask({"it": "Chi è?", "en": "Who is it?"}, [], {"kind": "who", "track": a["id"]}, allow_name=True)
    assert c.post(f"/api/confirm/{cid}", json={"value": {"known": viola.id}}).json()["ok"]
    settle(ctx)
    assert ctx.house.tracks[a["id"]].identity == viola.id


def test_something_pointed_at_on_the_plan_in_the_simulation(web):
    ctx, c = web
    ctx.sim.enabled = True
    r = c.post("/api/tracks/adopt", json={"x": 300, "y": 100}).json()
    assert r["ok"] and r["track"] in ctx.house.tracks
    assert c.post("/api/tracks/adopt", json={"u": 0.5}).status_code == 400


def test_ask_questions_from_a_phone(web):
    ctx, c = web
    r = c.post("/api/voice/ask", json={}).json()
    assert r["ok"] is False and r["error"] in ("no_voice", "nobody", "no_mic", "silent")


def test_the_recognition_waits_for_the_end_of_a_party(web):
    ctx, c = web
    from domotiq.app import _wire
    _wire(ctx)
    paused = []
    ctx.vision.pause = paused.append
    ctx.bus.publish("party", state="started", duration=20)
    ctx.bus.publish("party", state="ended")
    assert paused == [True, False]


def test_what_the_house_learned_is_corrected_and_forgotten(web):
    """An answer the house thought wrong, and a question heard wrong, corrected in the web app."""
    ctx, c = web
    k = ctx.knowledge
    k.learn("come si fa la pizza", "C'è un po' di tempo per preparare le uova.", generated=True)
    k.learn("come si fa la vita", "prendi farina lievito acqua e sale")
    listed = c.get("/api/knowledge").json()
    assert [i["q"] for i in listed] == ["come si fa la vita", "come si fa la pizza"]
    pizza, vita = listed[1], listed[0]
    r = c.put(f"/api/knowledge/{pizza['id']}", json={"answer": "acqua, farina, lievito e sale"})
    assert r.status_code == 200 and not r.json().get("generated")
    assert k.find("come si fa la pizza")["a"] == "acqua, farina, lievito e sale"
    r = c.put(f"/api/knowledge/{vita['id']}", json={"question": "come si fa il pane", "answer": vita["a"]})
    assert r.status_code == 200 and k.find("come si fa il pane")["a"] == vita["a"]
    assert k.find("come si fa la vita") is None
    assert c.put(f"/api/knowledge/{vita['id']}", json={"answer": " "}).status_code == 400
    assert c.delete(f"/api/knowledge/{vita['id']}").json()["ok"]
    assert c.delete(f"/api/knowledge/{vita['id']}").status_code == 404
    assert [i["q"] for i in c.get("/api/knowledge").json()] == ["come si fa la pizza"]
    log = c.get("/api/audit").json()
    assert {e["action"] for e in log if e["entity"] == "knowledge"} == {"update", "delete"}


def test_a_deleted_character_leaves_the_presences_the_questions_and_the_journal(web):
    """Deleted from the list of characters, it stayed elsewhere: proposed by an open question, on a presence for a
    moment, and among what the journal teaches the network."""
    ctx, c = web
    from domotiq.app import _wire
    _wire(ctx)
    ctx.sim.enabled = True
    a = c.post("/api/sim/objects", json={"x": 300, "y": 100, "category": "person", "color": "#d03030"}).json()
    b = c.post("/api/sim/objects", json={"x": 80, "y": 100, "category": "person", "color": "#20a0e0"}).json()
    settle(ctx)
    assert c.post(f"/api/tracks/{a['id']}/identity", json={"name": "Rosaria", "category": "person"}).json()["ok"]
    rosaria, viola = ctx.identities.by_name("Rosaria"), ctx.identities.add("Viola", "person")
    ctx.bus.publish("vision_question", track=dict(ctx.house.tracks[b["id"]].to_dict(), identity=viola.id),
                    candidates=[rosaria.id, viola.id])
    assert [o["value"] for o in c.get("/api/state").json()["confirmations"][0]["options"]] == [rosaria.id, viola.id]
    d = ctx.paths.journal
    (d / "journal.jsonl").write_text("".join(json.dumps({"id": f"20261010-10000{k}-000{k}", "t": 1.0, "kind": "nome",
                                                         "name": n, "figure": [n, 0.9]}) + "\n"
                                             for k, n in enumerate(["Rosaria", "Viola"])))
    assert c.post("/api/journal/20261010-100000-0000", json={"label": "Rosaria"}).json()["ok"]
    assert c.post("/api/journal/20261010-100001-0001", json={"label": "Viola"}).json()["ok"]
    assert c.delete(f"/api/identities/{rosaria.id}").status_code == 200
    state = c.get("/api/state").json()
    assert state["confirmations"] == []                                  # the question that proposed her is gone
    assert all(t["identity"] != rosaria.id for t in state["tracks"])     # at once, not at the next picture
    labels = {e["id"]: e["label"] for e in c.get("/api/journal").json()["entries"]}
    assert labels["20261010-100000-0000"] is None and labels["20261010-100001-0001"]["label"] == "Viola"
    assert "Rosaria" not in c.get("/api/journal").json()["names"]


def test_a_character_is_added_by_name_before_the_house_sees_it(web):
    """The characters of a house known before their figurines are put on it (a cat and a dog to come)."""
    ctx, c = web
    r = c.post("/api/identities", json={"name": "Romeo", "category": "cat", "color": "#f08020"})
    assert r.status_code == 200 and r.json()["category"] == "cat" and r.json()["signature"] is None
    romeo = ctx.identities.by_name("Romeo")
    assert romeo is not None and romeo.signature == [] and romeo.color == "#f08020"
    assert c.post("/api/identities", json={"name": "romeo", "category": "cat"}).status_code == 409
    assert c.post("/api/identities", json={"name": " ", "category": "cat"}).status_code == 400
    assert c.post("/api/identities", json={"name": "Fido", "category": "drago"}).status_code == 400
    assert any(e["action"] == "create" and e["entity"] == "identity" for e in c.get("/api/audit").json())


def test_a_character_learns_its_look_again(web):
    """The characters of a house copied onto another one built with its own figurines: their colours were those of
    the first house, and the second recognized nobody or the wrong one."""
    ctx, c = web
    viola = ctx.identities.add("Viola", "person", signature=[0.5] * 12, nickname="Tester")
    ctx.identities.update(viola.id, poses=[{"sig": [0.4] * 12, "area": 300.0}], size=310.0)
    ctx.identities.update(viola.id, facts=["ama il jazz"])
    r = c.post(f"/api/identities/{viola.id}/forget-look")
    assert r.status_code == 200 and r.json()["name"] == "Viola"
    v = ctx.identities.get(viola.id)
    assert v.signature == [] and v.poses == [] and not v.size and v.facts == ["ama il jazz"]
    assert any(e["action"] == "forget_look" and e["before"]["name"] == "Viola" for e in c.get("/api/audit").json())
    assert c.post("/api/identities/nobody/forget-look").status_code == 404


def test_the_journal_of_the_vision_is_reviewed_in_the_web_app(web):
    ctx, c = web
    d = ctx.paths.journal
    (d / "20261007-010000-0001.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (d / "journal.jsonl").write_text(json.dumps({"id": "20261007-010000-0001", "t": 1.0, "kind": "scartata",
                                                 "name": None, "figure": ["niente", 0.93]}) + "\n")
    r = c.get("/api/journal").json()
    assert [e["id"] for e in r["entries"]] == ["20261007-010000-0001"] and r["entries"][0]["label"] is None
    assert c.get("/api/journal/20261007-010000-0001.jpg").status_code == 200
    assert c.get("/api/journal/../config.jpg").status_code == 404
    assert c.post("/api/journal/20261007-010000-0001", json={"label": "Nessuno"}).status_code == 400
    assert c.post("/api/journal/20261007-010000-0001", json={"label": "niente"}).json()["ok"]
    assert c.get("/api/journal").json()["entries"][0]["label"]["label"] == "niente"
