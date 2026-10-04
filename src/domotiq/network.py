# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The Wi-Fi hotspot of the house, as far as the application touches it.

The hotspot is the NetworkManager connection `domotiq-hotspot` made by
scripts/hotspot.sh. Its password can be changed from the settings of the web app. The
sudo rules installed with the house allow exactly two things on it:
- /usr/local/sbin/domotiq-hotspot-psk, a small root-owned script that reads
  the new passphrase on its standard input, checks it and sets only that
  property (no wildcard rule that could change anything else of the
  connection, and the password never shows in the list of processes);
- `nmcli connection up domotiq-hotspot`, to restart it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

log = logging.getLogger(__name__)

CONNECTION = "domotiq-hotspot"
NMCLI = "/usr/bin/nmcli"
SET_PSK = "/usr/local/sbin/domotiq-hotspot-psk"


class HotspotError(RuntimeError):
    pass


def valid_password(password: str) -> bool:
    """WPA2 passphrase: 8 to 63 printable ASCII characters."""
    return 8 <= len(password) <= 63 and all(32 <= ord(c) <= 126 for c in password)


def available() -> bool:
    """NetworkManager is on this machine (not on a PC in simulation or in the tests)."""
    return shutil.which("nmcli") is not None and os.path.exists(NMCLI)


async def _run(*args: str, stdin: str | None = None) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(stdin.encode() if stdin is not None else None), timeout=20)
        return proc.returncode or 0, out.decode(errors="replace").strip()
    except (OSError, asyncio.TimeoutError) as e:
        return 1, str(e)


async def hotspot_state() -> tuple[bool, bool]:
    """(the hotspot connection exists, it is active now). Raises HotspotError if nmcli fails."""
    if not available():
        return False, False
    code, out = await _run(NMCLI, "-t", "-f", "NAME", "connection", "show")
    if code != 0:
        raise HotspotError(f"nmcli did not answer: {out[-200:]}")
    exists = CONNECTION in out.splitlines()
    code, out = await _run(NMCLI, "-t", "-f", "NAME", "connection", "show", "--active")
    if code != 0:
        raise HotspotError(f"nmcli did not answer: {out[-200:]}")
    return exists, CONNECTION in out.splitlines()


async def set_hotspot_password(password: str) -> None:
    """Write the new password into the hotspot connection, or raise HotspotError."""
    if not valid_password(password):
        raise HotspotError("the Wi-Fi password must be 8 to 63 characters")
    if not os.path.exists(SET_PSK):
        raise HotspotError(f"{SET_PSK} is missing: run scripts/install.sh again to update the system files")
    code, out = await _run("sudo", "-n", SET_PSK, stdin=password + "\n")
    if code != 0:
        raise HotspotError(f"the hotspot did not accept the password: {out[-200:]}")


async def restart_hotspot() -> bool:
    code, out = await _run("sudo", "-n", NMCLI, "connection", "up", CONNECTION)
    if code != 0:
        log.warning("hotspot restart failed: %s", out[-200:])
    return code == 0
