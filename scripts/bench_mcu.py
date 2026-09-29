# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Commissioning of the microcontroller and the Modulino, on the board.

    sudo systemctl stop domotiq             # the house must not use the bus at the same time
    venv/bin/python scripts/bench_mcu.py              # scan, lights, LEDs, then 20 s of buttons and sensors
    venv/bin/python scripts/bench_mcu.py --relay      # also switches the barbecue fan on for 2 s
    sudo systemctl start domotiq

Every step prints what it expects to see, so it can be followed alone at the
bench: each room lights red, green, blue and white in turn, the three LEDs
of the buttons light one after the other, then the script prints every
button press, distance and temperature the sketch reports.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from domotiq.layout import Layout  # noqa: E402
from domotiq.mcu import MODULES, Mcu, McuError, RouterClient  # noqa: E402

HUB_CHANNELS = {0: "Pixels garage", 1: "Pixels camera", 2: "Pixels cucina", 3: "Pixels soggiorno",
                4: "Thermo bagno", 5: "Pixels bagno", 6: "Thermo credenza, Buttons, Distance", 7: "libero"}
KNOWN = {0x36: "Pixels", 0x44: "Thermo", 0x3E: "Buttons", 0x29: "Distance", 0x02: "Latch Relay",
         0x15: "Latch Relay", 0x10: "Latch Relay (moved)"}
SOLID, OFF = 1, 0


def service_active() -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", "domotiq"]).returncode == 0
    except OSError:
        return False


async def main(args: argparse.Namespace) -> int:
    if service_active() and not args.force:
        print("The house is running: stop it first with  sudo systemctl stop domotiq  (or use --force).")
        return 2
    events: list[tuple[str, list]] = []
    client = RouterClient(args.router, on_notify=lambda n, p: events.append((n, p)))
    client.start()
    try:
        await asyncio.wait_for(client.connected.wait(), 10)
    except asyncio.TimeoutError:
        print("arduino-router does not answer: is the board up to date and the router running?")
        return 1
    mcu = Mcu(client)
    ok = await mcu.check()
    print(f"\n[1] Firmware: protocol {mcu.version}, {'OK' if ok else 'NOT OK (reload the firmware)'}")
    for name in MODULES:
        print(f"    {'ok     ' if mcu.modules[name] else 'MISSING'}  {name}")

    print("\n[2] Hub channels (7-bit addresses)")
    try:
        main_bus = await mcu.scan(255)
        names = ", ".join(f"0x{a:02x} {KNOWN.get(a, '')}".strip() for a in main_bus) or "nothing"
        print(f"    main bus: {names}")
    except McuError as e:
        print(f"    main bus: {e}")
    for ch, what in HUB_CHANNELS.items():
        try:
            found = [a for a in await mcu.scan(ch) if not 0x70 <= a <= 0x77]
            names = ", ".join(f"0x{a:02x} {KNOWN.get(a, '?')}" for a in found) or "nothing"
        except McuError as e:
            names = str(e)
        print(f"    ch{ch} ({what}): {names}")

    print("\n[3] Lights: every room red, green, blue, white")
    await mcu.limits(args.brightness, 450)
    layout = Layout.load()
    for light in sorted(layout.lights.values(), key=lambda li: li.index):
        print(f"    {light.room} (light {light.index}, hub channel {light.channel})")
        for r, g, b in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)):
            await mcu.light(light.index, SOLID, r, g, b, 100, 50)
            await asyncio.sleep(0.6)
        await mcu.light(light.index, OFF, 0, 0, 0, 0, 0)

    print("\n[4] Button LEDs: talk, intercom, language")
    for bit in range(3):
        await mcu.leds(1 << bit)
        await asyncio.sleep(0.8)
    await mcu.leds(0)

    if args.relay:
        print("\n[5] Latch Relay: the fan runs for 2 s")
        print(f"    on: {await mcu.relay(True)}")
        await asyncio.sleep(2.0)
        print(f"    off: {await mcu.relay(False)}")

    print(f"\n[6] For {args.listen} s: press the buttons, move a hand in front of the totem, breathe on a Thermo")
    events.clear()
    end = asyncio.get_running_loop().time() + args.listen
    shown = 0
    while asyncio.get_running_loop().time() < end:
        await asyncio.sleep(0.2)
        await mcu._call("ping")            # keeps the watchdog of the sketch quiet
        for name, params in events[shown:]:
            if name == "btn":
                print(f"    button {params[0]} {'pressed' if params[1] else 'released'}")
            elif name == "dist":
                print(f"    distance {params[0]} mm")
            elif name == "thermo":
                where = "bathroom" if params[0] == 1 else "thermostat"
                print(f"    {where}: {params[1] / 100:.1f} °C, {params[2] / 100:.0f} %")
            elif name == "mods":
                mcu.set_modules(int(params[0]))
                print(f"    modules changed: {[m for m, on in mcu.modules.items() if on]}")
        shown = len(events)
    await client.stop()
    print("\nDone. Start the house again with  sudo systemctl start domotiq")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--router", default="/run/arduino-router.sock")
    ap.add_argument("--relay", action="store_true", help="also switch the fan on for 2 s")
    ap.add_argument("--listen", type=float, default=20.0, help="seconds of buttons and sensors")
    ap.add_argument("--brightness", type=int, default=30, help="maximum brightness of the Pixels, %%")
    ap.add_argument("--force", action="store_true", help="run even if the house is running")
    sys.exit(asyncio.run(main(ap.parse_args())))
