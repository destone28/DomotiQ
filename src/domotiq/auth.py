# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Staff sessions: a PIN opens calibration, diagnostics and settings.

The hotspot is open to every visitor (its password is on the sign), and a
visitor can give their phone any address of the network, so wrong PINs are
counted in two ways:
- per address: 5 wrong PINs lock that address for a minute;
- for everybody: after 10 wrong PINs in 10 minutes, from anywhere, logins
  stop for a minute, then two, four... up to a quarter of an hour. The staff
  already logged in keep working; the PIN can always be changed on the board.
Changing the PIN or the Wi-Fi password also asks for the current PIN, and a
new PIN ends every other staff session.
"""

from __future__ import annotations

import secrets
import time

from .settings import Settings

MAX_ERRORS = 5              # per address
LOCK_S = 60
GLOBAL_ERRORS = 10          # from any address
GLOBAL_WINDOW_S = 600
GLOBAL_MAX_LOCK_S = 900


class StaffAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tokens: dict[str, float] = {}
        self._errors: dict[str, list[float]] = {}
        self._global: list[float] = []
        self._global_until = 0.0
        self._global_lock_s = LOCK_S

    def locked_for(self, client: str, now: float | None = None) -> float:
        now = time.time() if now is None else now
        if now < self._global_until:
            return self._global_until - now
        recent = [t for t in self._errors.get(client, []) if now - t < LOCK_S]
        self._errors[client] = recent
        if len(recent) >= MAX_ERRORS:
            return LOCK_S - (now - recent[0])
        return 0.0

    def _failed(self, client: str, now: float) -> None:
        self._errors.setdefault(client, []).append(now)
        self._global = [t for t in self._global if now - t < GLOBAL_WINDOW_S] + [now]
        if len(self._global) >= GLOBAL_ERRORS:
            self._global_until = now + self._global_lock_s
            self._global_lock_s = min(self._global_lock_s * 2, GLOBAL_MAX_LOCK_S)
            self._global = []

    def verify(self, pin: str, client: str, now: float | None = None) -> bool:
        """Check a PIN, counting a wrong one like a failed login."""
        now = time.time() if now is None else now
        if self.locked_for(client, now) > 0:
            return False
        if self.settings.check_pin(str(pin)):
            self._errors.pop(client, None)
            return True
        self._failed(client, now)
        return False

    def login(self, pin: str, client: str, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        if not self.verify(pin, client, now):
            return None
        if now >= self._global_until:
            self._global_lock_s = LOCK_S     # a good login resets the growing lock
        token = secrets.token_urlsafe(24)
        hours = float(self.settings.get("staff.session_hours", 12))
        self._tokens[token] = now + hours * 3600
        return token

    def check(self, token: str | None) -> bool:
        if not token:
            return False
        expires = self._tokens.get(token)
        if not expires:
            return False
        if expires < time.time():
            self._tokens.pop(token, None)
            return False
        return True

    def logout(self, token: str | None) -> None:
        if token:
            self._tokens.pop(token, None)

    def revoke_all(self, keep: str | None = None) -> int:
        """End every staff session but `keep` (after a PIN change)."""
        gone = [t for t in self._tokens if t != keep]
        for t in gone:
            self._tokens.pop(t, None)
        return len(gone)
