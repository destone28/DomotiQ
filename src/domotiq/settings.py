# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Settings of the house, persisted as JSON under var/config.

Every value has a default, so a freshly installed house works before anyone
opens the settings page. Unknown keys found on disk are kept, so a newer
configuration survives an older program.
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import tempfile
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
        "mic_gain": 100,             # capture level of the sound card, %
        "greet_phones": True,        # welcome aloud a phone that opens the web app for the first time
        "chatty_questions": True,    # in chatty mode, ask the characters questions now and then
        "question_every_s": 120,     # about how often (at least 45 s)
        "wake_enabled": False,       # the word of activation does what Talk does
        "wake_word": "Casa",
    },
    "lights": {
        "max_brightness": 30,        # cap applied by the firmware, 0-100
        "current_budget_ma": 450,    # firmware power limiter
        "follow": True,
        "follow_color": "#ffaa5a",
        "follow_favourite": True,    # in the normal scene, the light of a room takes the favourite colour of who is in
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
    "alarm": {"armed": True},        # off like a burglar alarm: the rules that raise alarms stay quiet
    "buttons": {"reversed": False},
    "network": {"ssid": "", "password": "", "channel": 1, "address": "", "hostname": ""},
    "camera": {"device": None,            # a /dev/v4l/by-id path, if the webcam is not found by itself
               "blur_bathroom": True,     # the bathroom blurred in the live view and the images that leave
               "figures": True,           # the network that knows the figurines gives its second opinion
               "figures_consent": False,  # ...and nothing new is told before it sees a figurine there
               "collect": False,          # what the webcam sees is kept to teach the network (var/collect)
               "collect_mb": 500,         # ...at most this much, the oldest goes
               "follow_light": True},     # the gain of the webcam follows the light of the hall step by step
    "clock": {"timezone": "Europe/Rome"},
}

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
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


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
        self.journal = root / "journal"           # what the vision told and refused, with its crops (for review)
        self.collect = root / "collect"           # what the webcam saw, kept to teach the network (when on)
        self.db = root / "domotiq.db"
        self.models = Path(os.environ.get("DOMOTIQ_MODELS", REPO_DIR / "models"))
        self.data = REPO_DIR / "data"
        for p in (self.config, self.photos, self.calibration, self.dataset, self.recordings, self.journal):
            p.mkdir(parents=True, exist_ok=True)


class Settings:
    def __init__(self, paths: Paths) -> None:
        self.path = paths.config / "settings.json"
        self._lock = threading.Lock()
        self._data = _merge(DEFAULTS, read_json(self.path, {}))
        self._mtime = self._disk_mtime()

    def _disk_mtime(self) -> int | None:
        try:
            return os.stat(self.path).st_mtime_ns
        except OSError:
            return None

    def _refresh_locked(self) -> None:
        """Another process (the admin command) may have written the file: never overwrite its changes."""
        m = self._disk_mtime()
        if m != self._mtime:
            self._data = _merge(DEFAULTS, read_json(self.path, {}))
            self._mtime = m

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
            self._refresh_locked()
            parts = dotted.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
            if save:
                write_json_atomic(self.path, self._data)
                self._mtime = self._disk_mtime()

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._refresh_locked()
            self._data = _merge(self._data, values)
            write_json_atomic(self.path, self._data)
            self._mtime = self._disk_mtime()

    def public(self) -> dict[str, Any]:
        """Everything, for the settings page (what an older version kept for the staff PIN is left out)."""
        d = copy.deepcopy(self._data)
        d.pop("staff", None)
        return d

    def save(self) -> None:
        with self._lock:
            write_json_atomic(self.path, self._data)
            self._mtime = self._disk_mtime()

