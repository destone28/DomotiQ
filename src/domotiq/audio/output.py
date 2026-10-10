# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The sound output: one ALSA stream that never closes, and a mixer in front of it.

Opening the stream for every sentence costs the first fraction of a second
of audio on this board. So one `aplay` process stays open from start to
end, fed with silence when there is nothing to say, and every sound goes
through the mixer: the voice, the party music (which ducks under the voice)
and the short effects.

Writes are paced on the wall clock with a small lead, and the pipe towards
aplay is shrunk, so what the mixer decides is heard within a fifth of a
second: a pipe left at its default size would queue more than a second.

The USB sound card can reset by itself (the US205 on casa1 did it several
times a day, reappearing within the same second with its levels back to the
factory ones). aplay does not always notice: it may stay alive on the card
that is gone, and a blocking write towards it would stop the mixer, and with
it every sentence of the house. So the writes never block, a stream that
stops taking sound for a second is started again, a card that comes back as
a new USB device is opened again with its levels set, and while there is no
card the sound is consumed on the clock all the same, so the house never
waits for a sentence that cannot be heard.

On a new board, on 10 October, the stream took sound for minutes after the
start and nothing was heard, until the guard opened it again: both times the
webcam, on the same USB hub, had reset just after the stream was opened (the
C270 of that house resets when it is opened, the one of casa1 does not). So
the stream is opened again once the webcam is open (reopen()), and the levels
of the card are read back every LEVELS_CHECK_S and set again if somebody
changed them.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import re
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from . import RATE, music, sounds

log = logging.getLogger(__name__)

CHUNK = RATE // 50                 # 20 ms
LEAD_S = 0.12                      # how far ahead of the clock the mixer may write
F_SETPIPE_SZ = 1031
STALL_S = 1.0                      # a stream that takes no sound for this long is started again
CARD_CHECK_S = 2.0                 # how often the card is checked (a reset makes it a new USB device)
LEVELS_CHECK_S = 10.0              # how often its levels are read back (amixer, some 15 ms, off the mixer thread)


def find_card(root: Path = Path("/proc/asound")) -> str | None:
    """The USB sound card, as an ALSA device name.

    The board has its own audio too, and the webcam is a USB sound card as
    well, with a microphone and nothing to play on: the card must have a
    playback device. Their numbers can swap from one boot to the next.
    """
    try:
        cards = (root / "cards").read_text()
    except OSError:
        return None
    for m in re.finditer(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s+(\S+)\s+-\s+(.*)$", cards, re.M):
        index, card_id, driver, _name = m.groups()
        if driver == "USB-Audio" and (root / f"card{index}" / "pcm0p").exists():
            return f"plughw:CARD={card_id},DEV=0"
    return None


def card_identity(device: str | None, root: Path = Path("/proc/asound")) -> str | None:
    """Which USB device the card is now ("001/010"): it changes when the card resets and comes back."""
    m = re.search(r"CARD=([^,]+)", device or "")
    if not m:
        return None
    try:
        cards = (root / "cards").read_text()
    except OSError:
        return None
    for idx, card_id in re.findall(r"^\s*(\d+)\s+\[(\S+)\s*\]", cards, re.M):
        if card_id == m.group(1):
            try:
                return (root / f"card{idx}" / "usbbus").read_text().strip() or f"card{idx}"
            except OSError:
                return f"card{idx}"
    return None


def mixer_commands(contents: str, mic_gain: int = 100) -> list[list[str]]:
    """amixer arguments that set the hardware levels of the card, from `amixer scontents`.

    Every playback volume goes to 100 %: the house sets the volume in
    software and the knob of the speakers stays at maximum, so the level
    the card remembers (38 %, -23 dB on the US205) must not get in the way.
    The microphone is captured at `mic_gain` % and never played back on the
    speakers, where it would howl.
    """
    out: list[list[str]] = []
    for block in re.split(r"^Simple mixer control ", contents, flags=re.M)[1:]:
        m = re.match(r"'([^']+)',(\d+)", block)
        caps = re.search(r"Capabilities:(.*)", block)
        if not m or not caps:
            continue
        name, caps_list = f"{m.group(1)},{m.group(2)}", caps.group(1).split()
        mic = "mic" in m.group(1).lower()
        if "pvolume" in caps_list or "pswitch" in caps_list:
            if mic:
                out.append([name, "playback", "0%", "mute"] if "pvolume" in caps_list else [name, "playback", "mute"])
            elif "pvolume" in caps_list:
                out.append([name, "playback", "100%", "unmute"])
        if mic and "cvolume" in caps_list:
            out.append([name, "capture", f"{max(0, min(100, int(mic_gain)))}%", "cap"])
    return out


def _part(line: str, which: str) -> tuple[int | None, str | None] | None:
    """The percent and the switch of the Playback or Capture part of a channel line of amixer (None if absent):
    "Mono: Playback 0 [0%] [-99999.99dB] [off] Capture 35 [100%] [23.00dB] [on]"."""
    m = re.search(rf"\b{which}\s+(.*?)(?=\s+(?:Playback|Capture)\s|$)", line)
    if not m:
        return None
    pct = re.search(r"\[(\d+)%\]", m.group(1))
    switch = re.search(r"\[(on|off)\]", m.group(1))
    return (int(pct.group(1)) if pct else None, switch.group(1) if switch else None)


def levels_ok(contents: str, mic_gain: int = 100) -> bool:
    """The levels of the card are those mixer_commands sets, from `amixer scontents`: every playback volume at
    100 % and on, the microphone silent on the speakers and captured at `mic_gain` %."""
    gain = max(0, min(100, int(mic_gain)))
    for block in re.split(r"^Simple mixer control ", contents, flags=re.M)[1:]:
        m = re.match(r"'([^']+)',(\d+)", block)
        caps = re.search(r"Capabilities:(.*)", block)
        if not m or not caps:
            continue
        caps_list, mic = caps.group(1).split(), "mic" in m.group(1).lower()
        channels = [line for line in block.splitlines()[1:]
                    if re.match(r"^\s+[^:]+:\s+(Playback|Capture)\s", line) and not line.strip().startswith("Limits")]
        for line in channels:
            playback, capture = _part(line, "Playback"), _part(line, "Capture")
            if playback and "pvolume" in caps_list and not mic and (playback[0] != 100 or playback[1] == "off"):
                return False
            if playback and mic and ("pvolume" in caps_list or "pswitch" in caps_list):
                silent = playback[1] == "off" or ("pvolume" in caps_list and playback[0] == 0)
                if not silent:
                    return False
            if capture and mic and "cvolume" in caps_list and capture[0] != gain:
                return False
    return True


def set_hardware_levels(device: str, mic_gain: int = 100) -> bool:
    m = re.search(r"CARD=([^,]+)", device)
    if not m:
        return False
    card = m.group(1)
    try:
        contents = subprocess.run(["amixer", "-c", card, "scontents"], capture_output=True, text=True,
                                  timeout=5).stdout
        for args in mixer_commands(contents, mic_gain):
            subprocess.run(["amixer", "-q", "-c", card, "sset", *args], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


class _Item:
    __slots__ = ("samples", "pos", "gain", "future", "loop", "kind")

    def __init__(self, samples: np.ndarray, kind: str, gain: float = 1.0,
                 future: asyncio.Future | None = None, loop: asyncio.AbstractEventLoop | None = None):
        self.samples = samples
        self.pos = 0
        self.gain = gain
        self.future = future
        self.loop = loop
        self.kind = kind

    def take(self, n: int) -> np.ndarray:
        part = self.samples[self.pos:self.pos + n]
        self.pos += n
        return part

    @property
    def done(self) -> bool:
        return self.pos >= len(self.samples)

    def finish(self, value: bool = True) -> None:
        if self.future is not None and self.loop is not None:
            fut = self.future
            self.loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(value))


class Audio:
    def __init__(self, settings: Any, device: str | None = None, dry: bool = False) -> None:
        self.settings = settings
        self.device = device or find_card()
        self.dry = dry or self.device is None
        self.ok = self.dry is False
        # no sound card at start: keep looking, it may be plugged in with the house already on
        self._waiting_card = not dry and self.device is None
        self._card_checked = 0.0
        self.latency_ms = int((LEAD_S + 0.1) * 1000)
        self._lock = threading.Lock()
        self._voice: deque[_Item] = deque()
        self._music: _Item | None = None
        self._effects: list[_Item] = []
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._volume = float(settings.get("voice.volume", 70)) / 100.0
        self.errors = 0
        self.last_error = ""
        self.restarts = 0
        self.levels_fixed = 0                      # times the levels of the card had changed and were set again
        self._levels_checked = 0.0
        self._levels_thread: threading.Thread | None = None
        self._reopen = ""                          # why the stream must be opened again (from another thread)
        self._identity: str | None = None          # the USB device the stream was opened on
        self._pending = b""                        # sound not yet taken by aplay

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="audio-mixer", daemon=True)
        self._thread.start()
        log.info("audio output: %s", self.device if not self.dry else
                 "no USB sound card yet, still looking" if self._waiting_card else "none (dry run)")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._close()

    def reopen(self, why: str) -> None:
        """Open the stream again, from the mixer thread: another USB device on the same hub reset."""
        self._reopen = why

    def _take_reopen(self) -> bool:
        """Close the stream if it was asked to open again (the loop opens it at once); True if it did."""
        why, self._reopen = self._reopen, ""
        if not why or self._proc is None:
            return False
        log.info("audio output opened again: %s", why)
        self._close()
        return True

    def set_volume(self, volume: int) -> None:
        self._volume = max(0.0, min(1.0, volume / 100.0))

    def status(self) -> dict[str, Any]:
        return {"ok": self.ok, "device": self.device or "", "dry": self.dry,
                "errors": self.errors, "last_error": self.last_error, "restarts": self.restarts,
                "levels_fixed": self.levels_fixed}

    # ------------------------------------------------------------ playing
    def _gain(self, key: str, default: int) -> float:
        return float(self.settings.get(f"voice.{key}", default)) / 100.0

    async def effect(self, name: str) -> None:
        samples = sounds.sound(name)
        with self._lock:
            self._effects.append(_Item(samples, "effect", self._gain("effects_gain", 80)))

    async def effect_wait(self, name: str) -> None:
        await self._play(sounds.sound(name), "effect", self._gain("effects_gain", 80))

    async def play_voice(self, samples: np.ndarray) -> None:
        await self._play(samples, "voice", self._gain("voice_gain", 100))

    async def _play(self, samples: np.ndarray, kind: str, gain: float) -> None:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        item = _Item(samples.astype(np.float32), kind, gain, fut, loop)
        with self._lock:
            if kind == "voice":
                self._voice.append(item)
            else:
                self._effects.append(item)
        await fut

    async def party_music(self, seed: int, duration: float, bpm: float) -> None:
        loop = asyncio.get_running_loop()
        samples = await loop.run_in_executor(None, music.render, seed, duration, bpm)
        fut = loop.create_future()
        with self._lock:
            if self._music:
                self._music.finish(False)
            self._music = _Item(samples, "music", self._gain("music_gain", 80), fut, loop)
        await fut

    def stop_music(self) -> None:
        with self._lock:
            if self._music:
                self._music.finish(False)
                self._music = None

    def stop_voice(self) -> None:
        with self._lock:
            for item in self._voice:
                item.finish(False)
            self._voice.clear()

    @property
    def speaking(self) -> bool:
        return bool(self._voice)

    # ------------------------------------------------------------ mixer
    def _mix(self) -> np.ndarray:
        out = np.zeros(CHUNK, dtype=np.float32)
        with self._lock:
            voice_on = bool(self._voice)
            if self._voice:
                item = self._voice[0]
                part = item.take(CHUNK)
                out[: len(part)] += part * item.gain
                if item.done:
                    self._voice.popleft()
                    item.finish()
            if self._music:
                part = self._music.take(CHUNK)
                out[: len(part)] += part * self._music.gain * (0.3 if voice_on else 1.0)
                if self._music.done:
                    self._music.finish()
                    self._music = None
            for item in list(self._effects):
                part = item.take(CHUNK)
                out[: len(part)] += part * item.gain
                if item.done:
                    self._effects.remove(item)
                    item.finish()
        out *= self._volume
        np.clip(out, -1.0, 1.0, out=out)
        return out

    def _open(self) -> bool:
        if self.dry:
            return True
        device = find_card() or self.device
        if device is None or card_identity(device) is None:
            self.ok = False
            return False
        self.device = device
        # the levels go back to the factory ones (-23 dB on the US205) at every reset of the card
        if not set_hardware_levels(self.device, int(self.settings.get("voice.mic_gain", 100))):
            log.warning("could not set the levels of %s", self.device)
        try:
            self._proc = subprocess.Popen(
                ["aplay", "-q", "-D", self.device, "-t", "raw", "-f", "S16_LE",
                 "-r", str(RATE), "-c", "1", "--buffer-time=100000"],
                stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            fd = self._proc.stdin.fileno()
            try:
                fcntl.fcntl(fd, F_SETPIPE_SZ, 4096)
            except OSError:
                pass
            os.set_blocking(fd, False)             # never wait for aplay: a stuck stream is noticed instead
            self._identity = card_identity(self.device)
            self._pending = b""
            self.ok = True
            return True
        except OSError as e:
            self.last_error = str(e)
            self.ok = False
            return False

    def _close(self) -> None:
        if self._proc:
            proc, self._proc = self._proc, None
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()                    # stuck on a card that is gone
                    proc.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        self._pending = b""

    def _check_levels(self) -> None:
        """Read the levels of the card back, and set them again if somebody changed them (its own thread: amixer
        must never hold up the mixer)."""
        m = re.search(r"CARD=([^,]+)", self.device or "")
        if not m:
            return
        mic_gain = int(self.settings.get("voice.mic_gain", 100))
        try:
            contents = subprocess.run(["amixer", "-c", m.group(1), "scontents"], capture_output=True, text=True,
                                      timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return
        if contents and not levels_ok(contents, mic_gain) and set_hardware_levels(self.device, mic_gain):
            self.levels_fixed += 1
            log.warning("the levels of the sound card %s had changed: set again", self.device)

    def _restart(self, why: str) -> None:
        self.errors += 1
        self.restarts += 1
        self.ok = False
        self.last_error = why[-200:]
        log.warning("audio output restarted: %s", why)
        self._close()

    def _write(self, data: bytes, now: float) -> None:
        """Hand the sound to aplay without ever blocking; a stream that takes nothing for STALL_S is stuck."""
        self._pending += data
        try:
            n = os.write(self._proc.stdin.fileno(), self._pending)
            self._pending = self._pending[n:]
            self._taken = now
        except BlockingIOError:
            pass
        except (BrokenPipeError, OSError, ValueError):
            self._pending = b""
            return
        if now - self._taken > STALL_S:
            self._restart("the sound card stopped taking sound")
        elif len(self._pending) > RATE:            # half a second of sound waiting: drop the oldest
            self._pending = self._pending[-RATE:]

    def _run(self) -> None:
        written = 0
        start = time.monotonic()
        retry_at = 0.0
        self._taken = start
        while self._running:
            now = time.monotonic()
            if self._waiting_card and now - self._card_checked > 5.0:
                self._card_checked = now
                card = find_card()
                if card:
                    self.device, self.dry, self._waiting_card = card, False, False
                    log.info("audio output: %s (plugged in)", card)
            if not self.dry:
                self._take_reopen()
                if self._proc is not None and self._proc.poll() is not None:
                    err = self._proc.stderr.read().decode(errors="replace") if self._proc.stderr else ""
                    self._restart(err.strip() or "aplay stopped")
                elif self._proc is not None and now - self._card_checked > CARD_CHECK_S:
                    self._card_checked = now
                    identity = card_identity(self.device)
                    if identity != self._identity:
                        self._restart(f"the sound card reset ({self._identity} -> {identity})")
                elif self._proc is not None and now - self._levels_checked > LEVELS_CHECK_S \
                        and not (self._levels_thread and self._levels_thread.is_alive()):
                    self._levels_checked = now
                    self._levels_thread = threading.Thread(target=self._check_levels, name="audio-levels",
                                                           daemon=True)
                    self._levels_thread.start()
                if self._proc is None and now >= retry_at:
                    if self._open():
                        log.info("audio output: %s", self.device)
                        self._taken = self._levels_checked = now
                        written, start = 0, now
                    else:
                        retry_at = now + 2.0
            ahead = written / RATE - (time.monotonic() - start)
            if ahead > LEAD_S:
                time.sleep(min(ahead - LEAD_S, 0.02))
                continue
            if ahead < -0.5:           # we fell behind (a hiccup): restart the clock
                written, start = 0, time.monotonic()
            # the sound is mixed on the clock even with no card: sentences end, and the house goes on
            chunk = self._mix()
            if self._proc is not None:
                self._write((chunk * 32767).astype("<i2").tobytes(), time.monotonic())
            written += CHUNK
