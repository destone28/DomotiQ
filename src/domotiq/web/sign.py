# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The A4 sign next to the house: join the Wi-Fi, open the web app."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import segno

if TYPE_CHECKING:
    from ..app import Context


def _escape(value: str) -> str:
    for ch in ("\\", ";", ",", '"', ":"):
        value = value.replace(ch, "\\" + ch)
    return value


def _svg(text: str) -> str:
    return segno.make(text, error="m").svg_inline(scale=8, border=2, dark="#1d2226")


def sign_data(ctx: "Context") -> dict[str, Any]:
    net = ctx.settings.get("network")
    number = ctx.settings.get("house.number", 1)
    ssid = net.get("ssid") or f"DomotiQ-Casa{number}"
    password = net.get("password") or ""
    address = net.get("address") or f"10.42.{number}.1"
    hostname = net.get("hostname") or socket.gethostname()
    url = f"http://{address}/"
    wifi = f"WIFI:T:WPA;S:{_escape(ssid)};P:{_escape(password)};;" if password else \
        f"WIFI:T:nopass;S:{_escape(ssid)};;"
    return {
        "house": ctx.settings.get("house.name"),
        "ssid": ssid,
        "password": password,
        "url": url,
        "name_url": f"http://{hostname}.lan/",
        "qr_wifi": _svg(wifi),
        "qr_url": _svg(url),
    }
