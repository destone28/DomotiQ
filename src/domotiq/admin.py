# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Change the staff PIN or the Wi-Fi password from the command line of the board.

    venv/bin/python -m domotiq.admin pin 4821
    venv/bin/python -m domotiq.admin wifi "new-password"

The same can be done from the web app (Settings, staff only). The house is
restarted afterwards, so it reads the new settings.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys

from . import network
from .settings import Paths, Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m domotiq.admin", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="what", required=True)
    sub.add_parser("pin", help="staff PIN, 4 to 8 digits").add_argument("value")
    sub.add_parser("wifi", help="password of the hotspot, 8 to 63 characters").add_argument("value")
    ap.add_argument("--var", default=None, help="data folder (default: var/ of the project)")
    args = ap.parse_args(argv)
    settings = Settings(Paths(args.var))
    if args.what == "pin":
        try:
            settings.set_pin(args.value)
        except ValueError as e:
            print(e)
            return 2
        print("Staff PIN changed.")
    else:
        if not network.valid_password(args.value):
            print("The Wi-Fi password must be 8 to 63 characters.")
            return 2
        exists, active = asyncio.run(network.hotspot_state())
        if exists:
            ok, error = asyncio.run(network.set_hotspot_password(args.value))
            if not ok:
                print(f"The hotspot did not accept the password: {error}")
                return 1
        settings.set("network.password", args.value)
        print("Wi-Fi password changed." + (" Restarting the hotspot: phones must join again." if active else ""))
        if active:
            asyncio.run(network.restart_hotspot())
    # the running house keeps its settings in memory: restart it so it reads the new ones
    if subprocess.run(["systemctl", "is-active", "--quiet", "domotiq"]).returncode == 0:
        subprocess.run(["sudo", "-n", "systemctl", "restart", "domotiq"])
        print("The house has been restarted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
