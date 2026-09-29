# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Speech recognition with Vosk, offline, in Italian and English.

Two ways of listening:
- a closed list of phrases (the names of the characters, yes and no, the
  options of a question): the small Vosk models accept a grammar at run
  time, which makes them fast and very hard to fool;
- free speech, for questions and commands, turned into an intent afterwards.

A grammar silently drops the words the model does not know, so every name
is checked against the model's vocabulary when it is registered.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

MODELS = {"it": "vosk-model-small-it-0.22", "en": "vosk-model-small-en-us-0.15"}
RATE = 16000


class Listener:
    def __init__(self, models_dir: Path) -> None:
        self.dir = Path(models_dir) / "vosk"
        self._models: dict[str, object] = {}
        self._vocab: dict[str, set[str]] = {}
        self._lock = threading.Lock()
        self.ok = False
        try:
            import vosk  # noqa: F401
            vosk.SetLogLevel(-1)
            self.ok = any((self.dir / m).exists() for m in MODELS.values())
        except ImportError:
            log.warning("vosk is not installed")

    def model(self, lang: str):
        with self._lock:
            if lang not in self._models:
                import vosk
                path = self.dir / MODELS[lang]
                if not path.exists():
                    raise FileNotFoundError(path)
                self._models[lang] = vosk.Model(str(path))
                log.info("speech model loaded: %s", MODELS[lang])
            return self._models[lang]

    def vocabulary(self, lang: str) -> set[str]:
        if lang not in self._vocab:
            words: set[str] = set()
            for candidate in ("graph/words.txt", "words.txt"):
                f = self.dir / MODELS[lang] / candidate
                if f.exists():
                    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                        w = line.split(" ", 1)[0].strip()
                        if w and not w.startswith(("#", "<")):
                            words.add(w)
                    break
            self._vocab[lang] = words
        return self._vocab[lang]

    def known(self, phrase: str, lang: str) -> bool:
        vocab = self.vocabulary(lang)
        if not vocab:
            return True             # cannot tell: assume yes
        return all(w in vocab for w in phrase.lower().split())

    def session(self, lang: str, grammar: list[str] | None = None) -> "Session":
        return Session(self, lang, grammar)


class Session:
    """Feed audio while it arrives; ask for the result at the end."""

    def __init__(self, listener: Listener, lang: str, grammar: list[str] | None) -> None:
        import vosk
        model = listener.model(lang)
        if grammar:
            words = [g.lower() for g in grammar if listener.known(g, lang)]
            self.rec = vosk.KaldiRecognizer(model, RATE, json.dumps(words + ["[unk]"], ensure_ascii=False))
        else:
            self.rec = vosk.KaldiRecognizer(model, RATE)
        self.rec.SetWords(True)
        self.parts: list[dict] = []

    def feed(self, pcm: bytes) -> None:
        if self.rec.AcceptWaveform(pcm):
            self.parts.append(json.loads(self.rec.Result()))

    def result(self) -> tuple[str, float]:
        self.parts.append(json.loads(self.rec.FinalResult()))
        words = [w for p in self.parts for w in p.get("result", [])]
        text = " ".join(p.get("text", "") for p in self.parts).strip()
        text = " ".join(t for t in text.split() if t != "[unk]")
        conf = sum(w.get("conf", 0) for w in words) / len(words) if words else 0.0
        return text, conf
