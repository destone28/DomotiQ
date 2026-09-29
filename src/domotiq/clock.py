# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The time of the house.

The UNO Q has no battery for its clock: after a power cut it wakes up with
whatever time it had when it was switched off. At a fair there is no NTP
either. So the clock takes the time from the first phone that opens the web
app, from a sentence ("it's half past three"), or from the staff.
"""

from __future__ import annotations

import logging
import subprocess
import time

log = logging.getLogger(__name__)


class HouseClock:
    def __init__(self, can_set: bool = True) -> None:
        self.can_set = can_set
        self.source = "system" if self.ntp_synced() else "unknown"
        self.set_at: float | None = None

    @property
    def known(self) -> bool:
        return self.source != "unknown"

    @staticmethod
    def ntp_synced() -> bool:
        try:
            out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                 capture_output=True, text=True, timeout=3)
            return out.stdout.strip() == "yes"
        except (OSError, subprocess.SubprocessError):
            return False

    def set(self, epoch: float, source: str) -> bool:
        """Set the system clock. Needs CAP_SYS_TIME (granted by the service).

        A phone sets it only while the house does not know the time: a visitor's
        phone with a wrong clock must not move the clock of a house that knows
        it. Corrections come from the staff or by voice.
        """
        drift = abs(epoch - time.time())
        if source == "phone" and self.known:
            return False
        if self.can_set and drift > 2:
            try:
                time.clock_settime(time.CLOCK_REALTIME, epoch)
            except (PermissionError, OSError) as e:
                log.warning("cannot set the clock: %s", e)
                if source != "phone":
                    return False
        self.source = source
        self.set_at = time.time()
        log.info("clock set from %s (drift %.0f s)", source, drift)
        return True

    def set_hm(self, hour: int, minute: int, source: str = "voice") -> bool:
        lt = time.localtime()
        target = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, minute, 0, 0, 0, -1))
        return self.set(target, source)

    def to_dict(self) -> dict:
        return {"now": time.time(), "known": self.known, "source": self.source,
                "timezone": time.strftime("%Z")}
