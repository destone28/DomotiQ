# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the staff page shows when something does not work."""

from __future__ import annotations

import glob
import logging
import os
import shutil
import socket
import subprocess
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import Context

log = logging.getLogger(__name__)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def cpu_temperature() -> float | None:
    temps = []
    for zone in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        v = _read(zone).strip()
        if v.lstrip("-").isdigit():
            temps.append(int(v) / 1000.0)
    return max(temps) if temps else None


def memory() -> dict[str, float]:
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            info[parts[0].rstrip(":")] = int(parts[1]) / 1024.0
    total = info.get("MemTotal", 0.0)
    avail = info.get("MemAvailable", 0.0)
    return {"total_mb": round(total), "available_mb": round(avail),
            "used_pct": round(100 * (1 - avail / total), 1) if total else None}


def wifi_clients() -> int | None:
    """Phones on the hotspot; None when the board is not the access point (on another
    network the only "station" is that network's router)."""
    try:
        info = subprocess.run(["iw", "dev", "wlan0", "info"], capture_output=True, text=True, timeout=3).stdout
        if "type AP" not in info:
            return None
        out = subprocess.run(["iw", "dev", "wlan0", "station", "dump"], capture_output=True,
                             text=True, timeout=3).stdout
        return out.count("Station ")
    except (OSError, subprocess.SubprocessError):
        return None


def uptime() -> float | None:
    v = _read("/proc/uptime").split()
    return float(v[0]) if v else None


async def collect(ctx: "Context") -> dict[str, Any]:
    disk = shutil.disk_usage(str(ctx.paths.var))
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
    return {
        "time": time.time(),
        "hostname": socket.gethostname(),
        "version": ctx.version,
        "uptime_s": uptime(),
        "app_uptime_s": time.time() - ctx.started if ctx.started else None,
        "cpu": {"load": [round(x, 2) for x in load], "cores": os.cpu_count(),
                "temperature": cpu_temperature()},
        "memory": memory(),
        "disk": {"free_mb": round(disk.free / 2**20), "total_mb": round(disk.total / 2**20)},
        "mcu": {"ok": ctx.mcu.ok, "version": ctx.mcu.version, "modules": ctx.mcu.modules,
                "relay": ctx.mcu.relay_state, "i2c": ctx.mcu.i2c},
        "camera": ctx.vision.status(),
        "audio": ctx.audio.status() if ctx.audio is not None else {"ok": False},
        "voice": ctx.voice.status() if ctx.voice is not None else {"ok": False},
        "wifi_clients": wifi_clients(),
        "phones": len(getattr(ctx, "hub_clients", []) or []),
        "clock": ctx.clock.to_dict(),
        "simulation": ctx.sim.enabled,
    }


def journal(lines: int = 500) -> str:
    try:
        return subprocess.run(["journalctl", "-u", "domotiq", "-n", str(lines), "--no-pager"],
                              capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return f"journal not available: {e}"


def system_action(what: str) -> None:
    """Restart the app, reboot or power off. The installer allows these with sudo."""
    if what == "restart":
        log.info("restart requested from the web app")
        os._exit(0)           # systemd starts the service again
    cmd = {"reboot": ["sudo", "-n", "systemctl", "reboot"],
           "shutdown": ["sudo", "-n", "systemctl", "poweroff"]}[what]
    try:
        subprocess.Popen(cmd)
    except OSError as e:
        log.error("%s failed: %s", what, e)
