# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The lavalier microphone in the intercom cap, through the USB sound card.

The microphone is open only while the house is listening: while the talk
button is held, or for a few seconds after "Who is it?". The audio stays in
memory and is never saved.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

MIC_RATE = 16000
CHUNK_BYTES = MIC_RATE // 10 * 2        # 100 ms of 16-bit mono


class Microphone:
    def __init__(self, device: str | None, follow: Callable[[], str | None] | None = None) -> None:
        self.device = device
        self.follow = follow                      # where to ask for the device when there is none
        self.last_level = 0.0

    @property
    def available(self) -> bool:
        if self.device is None and self.follow is not None:
            self.device = self.follow()           # the sound card may have been plugged in since
        return self.device is not None

    async def listen(self, stop: asyncio.Event, on_chunk: Callable[[bytes], None] | None = None,
                     max_s: float = 60.0, min_s: float = 0.0) -> bytes:
        """Record until `stop` is set (after at least `min_s`) or `max_s` passes."""
        if not self.available:
            try:
                await asyncio.wait_for(stop.wait(), timeout=max_s)
            except asyncio.TimeoutError:
                pass
            return b""
        proc = await asyncio.create_subprocess_exec(
            "arecord", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(MIC_RATE), "-c", "1", "-t", "raw",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        data = bytearray()
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            while True:
                elapsed = loop.time() - started
                if elapsed >= max_s or (stop.is_set() and elapsed >= min_s):
                    break
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(CHUNK_BYTES), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                data += chunk
                samples = np.frombuffer(chunk[: len(chunk) // 2 * 2], dtype="<i2")
                if samples.size:
                    self.last_level = float(np.sqrt(np.mean((samples / 32768.0) ** 2)))
                if on_chunk:
                    on_chunk(chunk)
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1)
                except asyncio.TimeoutError:
                    proc.kill()
        return bytes(data)
