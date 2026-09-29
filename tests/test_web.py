# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The web API, on a simulated house."""

from __future__ import annotations

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
    assert "text/html" in c.get("/sign").headers["content-type"]
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
    # rename and delete, with the trash for the staff
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


def test_staff_pin_and_lock(web):
    ctx, c = web
    assert c.get("/api/staff/settings").status_code == 401
    for _ in range(5):
        assert c.post("/api/staff/login", json={"pin": "9999"}).status_code == 403
    assert c.post("/api/staff/login", json={"pin": "0000"}).status_code == 429     # locked for a minute


def test_staff_session(web):
    ctx, c = web
    token = c.post("/api/staff/login", json={"pin": "0000"}).json()["token"]
    h = {"X-Staff": token}
    settings = c.get("/api/staff/settings", headers=h).json()
    assert "voice" in settings and "pin_hash" not in str(settings.get("staff", {}))
    diag = c.get("/api/staff/diagnostics", headers=h).json()
    assert "mcu" in diag
    assert c.get("/api/staff/backup.zip", headers=h).content[:2] == b"PK"


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


def test_staff_changes_the_wifi_password_and_pin(web, tmp_path):
    ctx, c = web
    h = {"X-Staff": c.post("/api/staff/login", json={"pin": "0000"}).json()["token"]}
    # a session alone is not enough: the current PIN is asked again
    assert c.post("/api/staff/network", json={"password": "casa-nuova-2026"}, headers=h).status_code == 403
    assert c.post("/api/staff/network", json={"password": "short", "current": "0000"}, headers=h).status_code == 400
    assert c.post("/api/staff/network", json={"password": "x" * 64, "current": "0000"}, headers=h).status_code == 400
    r = c.post("/api/staff/network", json={"password": "casa-nuova-2026", "current": "0000"}, headers=h).json()
    assert r["ok"] and not r["applied"] and r["reason"]     # no NetworkManager on a test machine: saved only
    assert ctx.settings.get("network.password") == "casa-nuova-2026"
    # the generic settings endpoint cannot change the network behind the hotspot's back
    c.put("/api/staff/settings", json={"network": {"password": "sneaky-pass"}}, headers=h)
    assert ctx.settings.get("network.password") == "casa-nuova-2026"
    assert c.post("/api/staff/network", json={"password": "casa-nuova-2026", "current": "0000"}).status_code == 401
    # PIN: needs the current one, then the old one no longer works and other sessions are over
    other = {"X-Staff": c.post("/api/staff/login", json={"pin": "0000"}).json()["token"]}
    assert c.post("/api/staff/pin", json={"pin": "4821"}, headers=h).status_code == 403
    assert c.post("/api/staff/pin", json={"pin": "12", "current": "0000"}, headers=h).status_code == 400
    r = c.post("/api/staff/pin", json={"pin": "4821", "current": "0000"}, headers=h).json()
    assert r["ok"] and r["sessions_ended"] == 1
    assert c.get("/api/staff/check", headers=h).status_code == 200
    assert c.get("/api/staff/check", headers=other).status_code == 401
    assert c.post("/api/staff/login", json={"pin": "0000"}).status_code == 403
    assert c.post("/api/staff/login", json={"pin": "4821"}).status_code == 200


def test_wrong_pins_from_many_addresses_lock_everybody(web):
    ctx, c = web
    from domotiq.auth import GLOBAL_ERRORS
    now = 1000.0
    for i in range(GLOBAL_ERRORS):
        assert ctx.auth.login("9999", f"10.42.1.{i + 10}", now + i) is None
    # a new address is locked too, and the lock grows while wrong PINs keep coming
    assert ctx.auth.locked_for("10.42.1.200", now + GLOBAL_ERRORS) > 0
    assert ctx.auth.login("0000", "10.42.1.201", now + GLOBAL_ERRORS) is None
    assert ctx.auth.login("0000", "10.42.1.201", now + GLOBAL_ERRORS + 61) is not None


def test_admin_command_line(tmp_path):
    from domotiq.admin import main
    from domotiq.settings import Paths, Settings
    var = str(tmp_path / "var")
    assert main(["--var", var, "pin", "12"]) == 2
    assert main(["--var", var, "pin", "7777"]) == 0
    assert main(["--var", var, "wifi", "short"]) == 2
    assert main(["--var", var, "wifi", "una-password-lunga"]) == 0
    s = Settings(Paths(var))
    assert s.check_pin("7777") and not s.check_pin("0000")
    assert s.get("network.password") == "una-password-lunga"
