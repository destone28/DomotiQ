# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Speech synthesis: the natural voice through the Piper HTTP server, the fast one through SVOX Pico.

Piper (piper1-gpl, GPL-3.0) is a separate program: it runs as its own
service in its own Python environment (`domotiq-tts`), and this module only
sends it text over HTTP on the loopback interface and gets WAV audio back.
Nothing of Piper is imported here. The fast voice (Settings -> Voice) is SVOX
Pico (`pico2wave`, Apache-2.0), also a separate program: plainer, but a
sentence is ready at once where Piper takes some tenths of a second on the
board. Without it the natural voice is used.

Sentences that the house says often are synthesized once and kept in memory,
so "Who is it?" plays at once even while the processor is busy. Every
sentence synthesized is also kept on disk (as Piper sent it, a WAV file named
after the voice and the text): after a restart it is read back in a moment
instead of being synthesized again, and the oldest go when there are too many.
The fixed sentences can be prepared ahead of time in another folder that is
only read (models/voice-cache, see scripts/voice_cache.py).

A few phrases are given to Piper as phonemes, where the Italian voice would
swallow a vowel: "Come si chiama?" came out as "Cme s chiama?", because
the phonemizer reads "si" as a reduced vowel.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import urllib.request
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import numpy as np

from ..audio import RATE

log = logging.getLogger(__name__)

VOICES = {"it": "it_IT-serena-medium", "en": "en_US-ljspeech-medium"}     # the natural voices (Piper)
FAST = {"it": "it-IT", "en": "en-US"}                                     # the fast voices (SVOX Pico)
PICO = "pico2wave"
PICO_SPEED = 140      # its own pace is slow: a sentence of 3.5 s for Piper took 5.3 s (4.7 s at 140, measured)
URL = "http://127.0.0.1:5010/synthesize"

# an interjection made of m and h only ("Mmm...", "Hmm,"): the voices spell it out letter by letter
HUM = (r"(?i)\b(h?m{2,}|hm+)\b[.,!?…]*\s*", "")

UNITS = {
    "it": [HUM, (r"(\d+)[.,](\d)\s*°\s*C?", r"\1 virgola \2 gradi"), (r"(\d+)\s*°\s*C?", r"\1 gradi"),
           (r"(\d+)\s*%", r"\1 per cento"), (r"\bWC\b", "vi ci"), (r"\bDomotiQ\b", "Dòmotik"),
           (r"\bUNO Q\b", "uno kiu"), (r"\bOK\b", "okèi"),
           (r"\b[Cc]ome si chiama\?", "[[ kˈome si kjˈaːma? ]]"), (r"\b[Cc]ome si chiama\b", "[[ kˈome si kjˈaːma ]]")],
    "en": [HUM, (r"(\d+)[.,](\d)\s*°\s*C?", r"\1 point \2 degrees"), (r"(\d+)\s*°\s*C?", r"\1 degrees"),
           (r"(\d+)\s*%", r"\1 percent"), (r"\bDomotiQ\b", "Domotic"), (r"\bUNO Q\b", "Uno Q")],
}


def normalize(text: str, lang: str, phonemes: bool = True) -> str:
    """Units, words to say otherwise and, for Piper (`phonemes`), the phrases given to it as phonemes."""
    for pattern, repl in UNITS.get(lang, []):
        if phonemes or "[[" not in repl:
            text = re.sub(pattern, repl, text)
    return text.strip()


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) == 0:
        return x
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Speaker:
    def __init__(self, url: str = URL, cache_size: int = 300, cache_dir: Path | str | None = None,
                 disk_max: int = 3000, seed_dir: Path | str | None = None,
                 voice: Callable[[], str] | None = None) -> None:
        self.url = url
        self.cache: OrderedDict[tuple[str, str], np.ndarray] = OrderedDict()
        self.cache_size = cache_size
        self.dir = Path(cache_dir) if cache_dir else None
        self.seed = Path(seed_dir) if seed_dir else None      # sentences prepared ahead of time, only read
        self.disk_max = disk_max
        self._written = 0
        self.ok = False
        self.errors = 0
        self.voice = voice                    # "natural" or "fast", asked at every sentence (Settings)
        self.fast_ok: bool | None = None      # SVOX Pico there (None: not tried yet)
        self._tmp = "/dev/shm" if os.path.isdir("/dev/shm") else None

    def current(self) -> str:
        """The voice the house speaks with now: the natural one if the fast one is missing."""
        wanted = self.voice() if self.voice else "natural"
        return "fast" if wanted == "fast" and self.fast_ok is not False else "natural"

    @staticmethod
    def voice_name(voice: str, lang: str) -> str:
        if voice == "fast":
            return f"pico-{FAST.get(lang, FAST['it'])}"
        return VOICES.get(lang, VOICES["it"])

    @staticmethod
    def _name(lang: str, text: str, voice_name: str | None = None) -> str:
        key = f"{voice_name or VOICES.get(lang, VOICES['it'])}\n{text}".encode()
        return f"{hashlib.sha1(key).hexdigest()[:24]}.wav"

    def _file(self, lang: str, text: str, voice_name: str | None = None) -> Path | None:
        return self.dir / self._name(lang, text, voice_name) if self.dir is not None else None

    def _from_disk(self, lang: str, text: str, voice_name: str | None = None) -> np.ndarray | None:
        for folder, own in ((self.dir, True), (self.seed, False)):
            if folder is None:
                continue
            f = folder / self._name(lang, text, voice_name)
            try:
                samples = self._decode(f.read_bytes())
                if own:
                    os.utime(f)                 # used: among the last to go
                return samples
            except (OSError, ValueError, EOFError, wave.Error):
                continue
        return None

    def _to_disk(self, lang: str, text: str, data: bytes, voice_name: str | None = None) -> None:
        f = self._file(lang, text, voice_name)
        if f is None:
            return
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".part")
            tmp.write_bytes(data)
            os.replace(tmp, f)
        except OSError as e:
            log.warning("a sentence could not be kept on disk: %s", e)
            return
        self._written += 1
        if self._written % 50 == 1:
            self._prune()

    def _prune(self) -> None:
        """Too many sentences on disk: the ones not said for the longest time go."""
        try:
            files = sorted(self.dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
            for p in files[:max(0, len(files) - self.disk_max)]:
                p.unlink(missing_ok=True)
        except OSError:
            pass

    def _synth(self, text: str, lang: str) -> np.ndarray:
        body = json.dumps({"text": text, "voice": VOICES.get(lang, VOICES["it"])}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as res:
            data = res.read()
        samples = self._decode(data)
        self._to_disk(lang, text, data)
        return samples

    def _synth_fast(self, text: str, lang: str) -> np.ndarray:
        """SVOX Pico: a WAV file written in memory (/dev/shm), read back and thrown away."""
        with tempfile.TemporaryDirectory(prefix="pico-", dir=self._tmp) as folder:
            out = Path(folder) / "s.wav"
            plain = re.sub(r"[<>&]", " ", text)
            subprocess.run([PICO, "-l", FAST.get(lang, FAST["it"]), "-w", str(out),
                            f'<speed level="{PICO_SPEED}">{plain}</speed>'], check=True, timeout=15, capture_output=True)
            data = out.read_bytes()
        samples = self._decode(data)
        self._to_disk(lang, text, data, self.voice_name("fast", lang))
        return samples

    @staticmethod
    def _decode(data: bytes) -> np.ndarray:
        with wave.open(io.BytesIO(data)) as w:
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
            channels = w.getnchannels()
        x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            x = x.reshape(-1, channels).mean(axis=1)
        # a short pause after each sentence sounds more natural
        return np.concatenate([_resample(x, rate, RATE), np.zeros(int(RATE * 0.12), np.float32)])

    def _keep(self, key: tuple[str, str], samples: np.ndarray) -> None:
        self.cache[key] = samples
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)

    async def synth(self, text: str, lang: str, fresh: bool = False) -> np.ndarray | None:
        """The audio of a sentence, in the voice chosen: from memory, from the disk, or synthesized (`fresh`: from
        Piper, to know that it answers)."""
        voice = "natural" if fresh else self.current()
        text = normalize(text, lang, phonemes=voice == "natural")
        if not text:
            return None
        name = self.voice_name(voice, lang)
        key = (name, text)
        loop = asyncio.get_running_loop()
        if not fresh:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            samples = await loop.run_in_executor(None, self._from_disk, lang, text, name)
            if samples is not None:
                self._keep(key, samples)
                return samples
        if voice == "fast":
            try:
                samples = await loop.run_in_executor(None, self._synth_fast, text, lang)
                self.fast_ok = True
                self._keep(key, samples)
                return samples
            except (OSError, ValueError, wave.Error, subprocess.SubprocessError) as e:
                log.warning("the fast voice is not there (%s): the natural voice speaks", e)
                self.fast_ok = False
                return await self.synth(text, lang)
        try:
            samples = await loop.run_in_executor(None, self._synth, text, lang)
            self.ok = True
        except (OSError, ValueError, wave.Error) as e:
            if self.ok or self.errors == 0:
                log.warning("speech synthesis failed: %s", e)      # once, not at every sentence
            self.ok = False
            self.errors += 1
            return None
        self._keep(key, samples)
        return samples

    async def warm(self, sentences: dict[str, list[str]], wait_s: float = 120.0) -> None:
        """The frequent sentences ready ahead of time: read back from the disk, and the ones never said yet
        synthesized once the Piper service answers.

        At boot the two services start together and Piper needs a few seconds
        to load its voice: one short sentence is synthesized, and retried,
        until it works (so the status tells whether Piper answers).
        """
        loop = asyncio.get_running_loop()
        missing = []
        voice = self.current()
        for lang, lines in sentences.items():
            for line in lines:
                text = normalize(line, lang, phonemes=voice == "natural")
                name = self.voice_name(voice, lang)
                samples = await loop.run_in_executor(None, self._from_disk, lang, text, name) if text else None
                if samples is not None:
                    self._keep((name, text), samples)
                elif text:
                    missing.append((lang, line))
        total = sum(len(v) for v in sentences.values())
        log.info("speech: %d frequent sentences read from the disk, %d to synthesize", total - len(missing),
                 len(missing))
        first_lang, first = missing[0] if missing else (next(iter(sentences), "it"), "Ok.")
        end = loop.time() + wait_s
        while await self.synth(first, first_lang, fresh=True) is None:
            if loop.time() > end:
                return
            await asyncio.sleep(3.0)
        log.info("speech synthesis ready")
        for lang, line in missing[1:]:
            await self.synth(line, lang)
