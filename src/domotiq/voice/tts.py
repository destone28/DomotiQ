# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Speech synthesis through the Piper HTTP server.

Piper (piper1-gpl, GPL-3.0) is a separate program: it runs as its own
service in its own Python environment (`domotiq-tts`), and this module only
sends it text over HTTP on the loopback interface and gets WAV audio back.
Nothing of Piper is imported here.

Sentences that the house says often are synthesized once and kept in memory,
so "Who is it?" plays at once even while the processor is busy.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import urllib.request
import wave
from collections import OrderedDict

import numpy as np

from ..audio import RATE

log = logging.getLogger(__name__)

VOICES = {"it": "it_IT-serena-medium", "en": "en_US-ljspeech-medium"}
URL = "http://127.0.0.1:5010/synthesize"

UNITS = {
    "it": [(r"(\d+)[.,](\d)\s*°\s*C?", r"\1 virgola \2 gradi"), (r"(\d+)\s*°\s*C?", r"\1 gradi"),
           (r"(\d+)\s*%", r"\1 per cento"), (r"\bWC\b", "vi ci"), (r"\bDomotiQ\b", "Dòmotik"),
           (r"\bUNO Q\b", "uno kiu"), (r"\bOK\b", "okèi")],
    "en": [(r"(\d+)[.,](\d)\s*°\s*C?", r"\1 point \2 degrees"), (r"(\d+)\s*°\s*C?", r"\1 degrees"),
           (r"(\d+)\s*%", r"\1 percent"), (r"\bDomotiQ\b", "Domotic"), (r"\bUNO Q\b", "Uno Q")],
}


def normalize(text: str, lang: str) -> str:
    for pattern, repl in UNITS.get(lang, []):
        text = re.sub(pattern, repl, text)
    return text.strip()


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) == 0:
        return x
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Speaker:
    def __init__(self, url: str = URL, cache_size: int = 300) -> None:
        self.url = url
        self.cache: OrderedDict[tuple[str, str], np.ndarray] = OrderedDict()
        self.cache_size = cache_size
        self.ok = False
        self.errors = 0

    def _synth(self, text: str, lang: str) -> np.ndarray:
        body = json.dumps({"text": text, "voice": VOICES.get(lang, VOICES["it"])}).encode()
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as res:
            data = res.read()
        with wave.open(io.BytesIO(data)) as w:
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
            channels = w.getnchannels()
        x = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            x = x.reshape(-1, channels).mean(axis=1)
        # a short pause after each sentence sounds more natural
        return np.concatenate([_resample(x, rate, RATE), np.zeros(int(RATE * 0.12), np.float32)])

    async def synth(self, text: str, lang: str) -> np.ndarray | None:
        text = normalize(text, lang)
        if not text:
            return None
        key = (lang, text)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        try:
            samples = await asyncio.get_running_loop().run_in_executor(None, self._synth, text, lang)
            self.ok = True
        except (OSError, ValueError, wave.Error) as e:
            if self.ok or self.errors == 0:
                log.warning("speech synthesis failed: %s", e)      # once, not at every sentence
            self.ok = False
            self.errors += 1
            return None
        self.cache[key] = samples
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return samples

    async def warm(self, sentences: dict[str, list[str]], wait_s: float = 120.0) -> None:
        """Synthesize the frequent sentences ahead of time, once the Piper service answers.

        At boot the two services start together and Piper needs a few seconds
        to load its voice: the first sentence is retried until it works.
        """
        first_lang = next(iter(sentences), "it")
        first = (sentences.get(first_lang) or ["Ciao"])[0]
        loop = asyncio.get_running_loop()
        end = loop.time() + wait_s
        while await self.synth(first, first_lang) is None:
            if loop.time() > end:
                return
            await asyncio.sleep(3.0)
        log.info("speech synthesis ready")
        for lang, lines in sentences.items():
            for line in lines:
                await self.synth(line, lang)
