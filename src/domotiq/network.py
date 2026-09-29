# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The Wi-Fi hotspot of the house, as far as the application touches it.

The hotspot is the NetworkManager connection `domotiq-hotspot` made by
scripts/hotspot.sh. The staff can change its password from the web app: the
sudo rules installed with the house allow exactly two nmcli commands on that
connection (modify it, bring it up), nothing else.
"""

from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)

CONNECTION = "domotiq-hotspot"
NMCLI = "/usr/bin/nmcli"


def valid_password(password: str) -> bool:
    """WPA2 passphrase: 8 to 63 printable ASCII characters."""
    return 8 <= len(password) <= 63 and all(32 <= ord(c) <= 126 for c in password)


async def _run(*args: str, sudo: bool = False) -> tuple[int, str]:
    cmd = (["sudo", "-n"] if sudo else []) + list(args)
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        return proc.returncode or 0, out.decode(errors="replace").strip()
    except (OSError, asyncio.TimeoutError) as e:
        return 1, str(e)


async def hotspot_state() -> tuple[bool, bool]:
    """(the hotspot connection exists, it is active now)."""
    if not shutil.which("nmcli"):
        return False, False
    code, out = await _run(NMCLI, "-t", "-f", "NAME", "connection", "show")
    exists = code == 0 and CONNECTION in out.splitlines()
    code, out = await _run(NMCLI, "-t", "-f", "NAME", "connection", "show", "--active")
    return exists, code == 0 and CONNECTION in out.splitlines()


async def set_hotspot_password(password: str) -> tuple[bool, str]:
    """Write the new password into the hotspot connection. (done, error)."""
    code, out = await _run(NMCLI, "connection", "modify", CONNECTION, "wifi-sec.psk", password, sudo=True)
    return code == 0, "" if code == 0 else out[-200:]


async def restart_hotspot() -> bool:
    code, out = await _run(NMCLI, "connection", "up", CONNECTION, sudo=True)
    if code != 0:
        log.warning("hotspot restart failed: %s", out[-200:])
    return code == 0
