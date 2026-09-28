# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Staff sessions: a PIN opens calibration, diagnostics and settings."""

from __future__ import annotations

import secrets
import time

from .settings import Settings

MAX_ERRORS = 5
LOCK_S = 60


class StaffAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tokens: dict[str, float] = {}
        self._errors: dict[str, list[float]] = {}

    def locked_for(self, client: str) -> float:
        now = time.time()
        recent = [t for t in self._errors.get(client, []) if now - t < LOCK_S]
        self._errors[client] = recent
        if len(recent) >= MAX_ERRORS:
            return LOCK_S - (now - recent[0])
        return 0.0

    def login(self, pin: str, client: str) -> str | None:
        if self.locked_for(client) > 0:
            return None
        if not self.settings.check_pin(str(pin)):
            self._errors.setdefault(client, []).append(time.time())
            return None
        self._errors.pop(client, None)
        token = secrets.token_urlsafe(24)
        hours = float(self.settings.get("staff.session_hours", 12))
        self._tokens[token] = time.time() + hours * 3600
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
