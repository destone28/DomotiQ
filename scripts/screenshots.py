# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Screenshots of the web app for the guides, in Italian and English.

Runs the house in simulation with a few characters, then drives a headless
Chrome through its DevTools protocol at phone size. On a PC:

    .venv/bin/python scripts/screenshots.py            # into docs/images/screens/{it,en}
    .venv/bin/python scripts/screenshots.py --out /tmp/shots
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
SCREENS = [
    ("home", "#/home"), ("live", "#/live"), ("commands", "#/commands"), ("events", "#/events"),
    ("more", "#/more"), ("rules", "#/rules"), ("rule-edit", "#/rules?edit=r-utility-forbidden"),
    ("identities", "#/identities"), ("sim", "#/sim"), ("calibration", "#/calibration"),
    ("settings", "#/settings"),
]
# the diagnostics show the computer they run on: they are taken from a real house instead


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(base: str, method: str, path: str, body=None, headers=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Nickname": "Demo",
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


def populate(base: str) -> None:
    """A few characters in the house, one of them registered by the tests of the stand."""
    people = [("Marco", "person", "#d03030", 300, 110), ("Sofia", "person", "#3050d0", 90, 150),
              ("Fido", "dog", "#b07a3a", 110, 300), ("Auto", "car", "#e8e8e8", 540, 300)]
    for name, cat, color, x, y in people:
        obj = call(base, "POST", "/api/sim/objects", {"x": x, "y": y, "category": cat, "color": color})
        time.sleep(0.6)
        s = call(base, "POST", "/api/register", {"name": name, "category": cat})
        if s.get("status") == "choose":
            s = call(base, "POST", f"/api/register/{s['id']}/pick", {"track": obj["id"]})
        if s.get("status") == "confirm":
            call(base, "POST", f"/api/register/{s['id']}/confirm", {"category": cat})
    call(base, "POST", "/api/sim/objects", {"x": 520, "y": 120, "category": "person", "color": "#20a060"})
    call(base, "POST", "/api/commands/scene", {"scene": "relax"})
    time.sleep(1.0)


class Tab:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.n = 0

    async def send(self, method: str, **params):
        self.n += 1
        mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mid:
                return msg.get("result", {})


async def shoot(base: str, out: Path, debug_port: int) -> None:
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json").read())
    page = next(t for t in targets if t["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
        tab = Tab(ws)
        await tab.send("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2,
                       mobile=True)
        await tab.send("Page.enable")
        for lang in ("it", "en"):
            (out / lang).mkdir(parents=True, exist_ok=True)
            await tab.send("Page.navigate", url=base + "/")
            await asyncio.sleep(1.5)
            await tab.send("Runtime.evaluate", expression=(
                f"localStorage.setItem('domotiq.lang','{lang}');"
                "localStorage.setItem('domotiq.nickname','Demo');"))
            # the language is read when the page loads
            await tab.send("Page.reload", ignoreCache=True)
            await asyncio.sleep(1.5)
            # no welcome card for this phone, and no subtitles of what the house says over the pages
            await tab.send("Runtime.evaluate", expression=(
                "fetch('/api/welcome',{method:'POST',headers:{'Content-Type':'application/json',"
                "'X-Device':localStorage.getItem('domotiq.device')},body:JSON.stringify({later:true})});"
                "const st=document.createElement('style');st.textContent='#subtitle{display:none!important}';"
                "document.head.appendChild(st);"))
            for name, hash_ in SCREENS:
                await tab.send("Page.navigate", url=f"{base}/{hash_}")
                await asyncio.sleep(2.5)
                await tab.send("Runtime.evaluate", expression=(
                    "document.querySelectorAll('#modal [data-a=later]').forEach(b=>b.click());"))
                await asyncio.sleep(0.3)
                shot = await tab.send("Page.captureScreenshot", format="png")
                (out / lang / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
                print(f"{lang}/{name}.png")
        # the A4 sign, once (it is bilingual)
        await tab.send("Emulation.setDeviceMetricsOverride", width=794, height=1123, deviceScaleFactor=1.5,
                       mobile=False)
        await tab.send("Page.navigate", url=base + "/sign")
        await asyncio.sleep(2.0)
        shot = await tab.send("Page.captureScreenshot", format="png")
        (out / "sign.png").write_bytes(base64.b64decode(shot["data"]))
        print("sign.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "images" / "screens"))
    ap.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chromium") or "chromium")
    args = ap.parse_args()
    out = Path(args.out)
    port, debug_port = free_port(), free_port()
    var = Path(tempfile.mkdtemp(prefix="domotiq-shots-"))
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    app = subprocess.Popen([sys.executable, "-m", "domotiq.app", "--simulate", "--no-audio", "--no-voice",
                            "--port", str(port), "--host", "127.0.0.1", "--var", str(var)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    profile = tempfile.mkdtemp(prefix="domotiq-chrome-")
    chrome = subprocess.Popen([args.chrome, "--headless=new", f"--remote-debugging-port={debug_port}",
                               f"--user-data-dir={profile}", "--no-first-run", "--hide-scrollbars",
                               "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/state", timeout=1)
                urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        populate(base)
        asyncio.run(shoot(base, out, debug_port))
    finally:
        chrome.terminate()
        app.terminate()
        shutil.rmtree(var, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
