# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Settings of the house, persisted as JSON under var/config.

Every value has a default, so a freshly installed house works before anyone
opens the settings page. Unknown keys found on disk are kept, so a newer
configuration survives an older program.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Any

REPO_DIR = Path(__file__).resolve().parents[2]

DEFAULTS: dict[str, Any] = {
    "house": {"number": 1, "name": {"it": "Casa 1", "en": "House 1"}},
    "voice": {
        "language": "it",            # language the house speaks and listens in
        "verbosity": "normal",       # silent | normal | chatty
        "volume": 70,                # master, 0-100
        "voice_gain": 100,
        "music_gain": 80,
        "effects_gain": 80,
    },
    "lights": {
        "max_brightness": 30,        # cap applied by the firmware, 0-100
        "current_budget_ma": 450,    # firmware power limiter
        "follow": True,
        "follow_color": "#ffaa5a",
        "follow_brightness": 60,
        "follow_off_delay_s": 3,
    },
    "party": {"duration_s": 20, "cooldown_s": 30, "bpm": 124},
    "grill": {"duration_s": 20, "max_on_s": 120, "cooldown_s": 30},
    "climate": {
        "hot_delta": 1.0,            # °C above the baseline
        "hot_rate": 0.1,             # °C per second
        "cold_delta": 1.0,
        "release_delta": 0.5,
        "breath_rh_delta": 10.0,     # humidity jump when someone blows on it
        "shower_rh_delta": 8.0,
        "shower_release": 3.0,
        "baseline_s": 300,
    },
    "garage": {"parked_after_s": 3, "absent_after_s": 10, "light_off_after_s": 10},
    "constraints": {"utility_grace_s": 5, "bathroom_max": 1},
    "buttons": {"reversed": False},
    "staff": {"pin_hash": None, "pin_salt": None, "session_hours": 12},
    "network": {"ssid": "", "password": "", "channel": 1, "address": "", "hostname": ""},
    "camera": {"device": None},           # a /dev/v4l/by-id path, if the webcam is not found by itself
    "clock": {"timezone": "Europe/Rome"},
}

DEFAULT_PIN = "0000"


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(default)
    except (OSError, json.JSONDecodeError):
        # a damaged file must not stop the house: keep a copy and start over
        try:
            os.replace(path, path.with_suffix(path.suffix + ".damaged"))
        except OSError:
            pass
        return copy.deepcopy(default)


class Paths:
    """Where the house keeps what it remembers."""

    def __init__(self, var_dir: Path | str | None = None) -> None:
        root = Path(var_dir or os.environ.get("DOMOTIQ_VAR", REPO_DIR / "var"))
        self.var = root
        self.config = root / "config"
        self.photos = root / "photos"
        self.calibration = root / "calibration"
        self.dataset = root / "dataset"
        self.recordings = root / "recordings"
        self.db = root / "domotiq.db"
        self.models = Path(os.environ.get("DOMOTIQ_MODELS", REPO_DIR / "models"))
        self.data = REPO_DIR / "data"
        for p in (self.config, self.photos, self.calibration, self.dataset, self.recordings):
            p.mkdir(parents=True, exist_ok=True)


class Settings:
    def __init__(self, paths: Paths) -> None:
        self.path = paths.config / "settings.json"
        self._lock = threading.Lock()
        self._data = _merge(DEFAULTS, read_json(self.path, {}))

    # ------------------------------------------------------------ access
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return copy.deepcopy(node)

    def set(self, dotted: str, value: Any, save: bool = True) -> None:
        with self._lock:
            parts = dotted.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
            if save:
                write_json_atomic(self.path, self._data)

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data = _merge(self._data, values)
            write_json_atomic(self.path, self._data)

    def public(self) -> dict[str, Any]:
        """Everything except secrets, for the settings page."""
        d = copy.deepcopy(self._data)
        d["staff"] = {"session_hours": d["staff"].get("session_hours", 12),
                      "pin_set": bool(d["staff"].get("pin_hash"))}
        return d

    def save(self) -> None:
        with self._lock:
            write_json_atomic(self.path, self._data)

    # ------------------------------------------------------------ staff PIN
    def set_pin(self, pin: str) -> None:
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            raise ValueError("the PIN must be 4 to 8 digits")
        salt = secrets.token_hex(8)
        self.set("staff.pin_salt", salt, save=False)
        self.set("staff.pin_hash", _hash_pin(pin, salt))

    def check_pin(self, pin: str) -> bool:
        salt = self.get("staff.pin_salt")
        stored = self.get("staff.pin_hash")
        if not stored:
            return secrets.compare_digest(pin, DEFAULT_PIN)
        return secrets.compare_digest(_hash_pin(pin, salt or ""), stored)


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
