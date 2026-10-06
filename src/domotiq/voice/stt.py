# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Speech recognition with Vosk, offline, in Italian and English.

Two ways of listening:
- a closed list of phrases (the names of the characters, yes and no, the
  options of a question): the small Vosk models accept a grammar at run
  time, which makes them fast and very hard to fool;
- free speech, for questions and commands, turned into an intent afterwards;
  for a request the recognizer also gives the other sentences it found likely
  (alternatives), and the first one the rules understand is taken.

A grammar silently drops the words the model does not know, so every name
is checked against the model's vocabulary when it is registered, and a name
the model does not know is listened for with a spelling it knows
("rossellina" as "rosellina"), turned back into the name when heard.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

MODELS = {"it": "vosk-model-small-it-0.22", "en": "vosk-model-small-en-us-0.15"}
RATE = 16000


# letters an Italian word does not have, written as they sound ("domotiq" is said "domotic")
SOUNDS = [("ck", "c"), ("ph", "f"), ("th", "t"), ("qu", "cu"), ("q", "c"), ("k", "c"), ("w", "v"), ("y", "i"),
          ("x", "s"), ("j", "i")]


def respellings(word: str) -> list[str]:
    """Other spellings of a word, closest first, for a model that does not know it: its double letters written
    single ("rossellina": "rosellina", "rosselina", "roselina"), then each of these as two words of three letters
    at least ("rosse lina", "rose lina"). Then the word as it sounds, with no letters foreign to Italian
    ("domotiq": "domotic"), with a vowel at the end when it ends with a consonant ("domotica", "domotico"), and as
    two words."""
    doubles = [i for i in range(len(word) - 1) if word[i] == word[i + 1] and word[i].isalpha()]
    forms = [word]
    for i in doubles:
        forms.append(word[:i] + word[i + 1:])
    if len(doubles) > 1:
        forms.append("".join(c for i, c in enumerate(word) if i not in doubles))
    out = forms[1:]
    for f in forms:
        out += [f"{f[:i]} {f[i:]}" for i in range(3, len(f) - 2)]
    sounded = word
    for letters, sound in SOUNDS:
        sounded = sounded.replace(letters, sound)
    if sounded != word:
        out.append(sounded)
    if sounded[-1:].isalpha() and sounded[-1] not in "aeiou":
        out += [sounded + v for v in "aoei"]
    if sounded != word:
        out += [f"{sounded[:i]} {sounded[i:]}" for i in range(3, len(sounded) - 2)]
    return list(dict.fromkeys(f for f in out if f != word))


class Listener:
    def __init__(self, models_dir: Path) -> None:
        self.dir = Path(models_dir) / "vosk"
        self._models: dict[str, object] = {}
        self._vocab: dict[str, set[str]] = {}
        self._known: dict[tuple[str, str], bool] = {}
        self._spelling: dict[tuple[str, str], str | None] = {}
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
        words = phrase.lower().split()
        if vocab:
            return all(w in vocab for w in words)
        return all(self._known_by_grammar(w, lang) for w in words)

    def spelling(self, phrase: str, lang: str) -> str | None:
        """The phrase as the model can hear it: itself, or with a spelling it knows for each word it does not
        know (a name: "rossellina" as "rosellina"); None when there is none."""
        key = (lang, phrase)
        if lang not in self._models and not self.vocabulary(lang):
            return phrase           # nothing to ask yet (see known): worked out once the model is loaded
        if key not in self._spelling:
            words = []
            for w in phrase.split():
                if not self.known(w, lang):
                    w = next((r for r in respellings(w) if self.known(r, lang)), None)
                    if w is None:
                        break
                words.append(w)
            else:
                self._spelling[key] = " ".join(words)
                return self._spelling[key]
            self._spelling[key] = None
        return self._spelling[key]

    def _known_by_grammar(self, word: str, lang: str) -> bool:
        """The small models have no word list: Vosk warns about the words of a grammar it lacks.

        The warning is written by the C++ library on the standard error, so
        that is captured for the instant the grammar is built.
        """
        key = (lang, word)
        if key in self._known:
            return self._known[key]
        if lang not in self._models:
            return True             # loading a model takes seconds: only the ones in use are asked
        import vosk
        model = self._models[lang]
        with self._lock:
            r, w = os.pipe()
            saved = os.dup(2)
            try:
                os.dup2(w, 2)
                # unescaped like the grammar itself: Vosk does not decode "\u00ec", and every accented
                # word ("sì", "perché") looked missing and was left out of the grammars
                vosk.KaldiRecognizer(model, RATE, json.dumps([word, "[unk]"], ensure_ascii=False))
            finally:
                os.dup2(saved, 2)
                os.close(saved)
                os.close(w)
            os.set_blocking(r, False)
            try:
                out = os.read(r, 65536).decode(errors="ignore")
            except BlockingIOError:
                out = ""
            os.close(r)
        ok = "missing in vocabulary" not in out.lower() and "ignoring word" not in out.lower()
        self._known[key] = ok
        return ok

    def session(self, lang: str, grammar: list[str] | None = None, respell: bool = True,
                alternatives: int = 0) -> "Session":
        return Session(self, lang, grammar, respell, alternatives)


class Session:
    """Feed audio while it arrives; ask for the result at the end. With a grammar and `respell`, a phrase the model
    does not know is listened for with a spelling it knows, and the results have the phrase itself.

    With `alternatives`, the recognizer also keeps that many likely sentences (`alternatives()`); it then gives no
    confidence word by word, and the confidence of the result is how much likelier the best sentence is than the
    others."""

    def __init__(self, listener: Listener, lang: str, grammar: list[str] | None, respell: bool = True,
                 alternatives: int = 0) -> None:
        import vosk
        model = listener.model(lang)
        self._back: dict[str, str] = {}
        if grammar:
            words = []
            for g in dict.fromkeys(g.lower() for g in grammar):
                heard = listener.spelling(g, lang) if respell else (g if listener.known(g, lang) else None)
                if heard is None:
                    continue
                words.append(heard)
                if heard != g:
                    self._back[heard] = g
            self.rec = vosk.KaldiRecognizer(model, RATE, json.dumps(words + ["[unk]"], ensure_ascii=False))
        else:
            self.rec = vosk.KaldiRecognizer(model, RATE)
        if alternatives:
            self.rec.SetMaxAlternatives(alternatives)
        self.rec.SetWords(True)
        self.parts: list[dict] = []

    def _phrases(self, text: str) -> str:
        """The phrases of the grammar heard with another spelling, written as themselves."""
        if not self._back:
            return text
        words, out, i = text.split(), [], 0
        while i < len(words):
            for heard, phrase in self._back.items():
                h = heard.split()
                if words[i:i + len(h)] == h:
                    out.append(phrase)
                    i += len(h)
                    break
            else:
                out.append(words[i])
                i += 1
        return " ".join(out)

    def feed(self, pcm: bytes) -> None:
        if self.rec.AcceptWaveform(pcm):
            self.parts.append(json.loads(self.rec.Result()))

    def feed_partial(self, pcm: bytes) -> str:
        """Feed, and tell what has been heard so far: the words of an utterance just ended, or the partial result of
        the one going on (it comes at once, while the word is still being said, without the confidence)."""
        if self.rec.AcceptWaveform(pcm):
            part = json.loads(self.rec.Result())
            self.parts.append(part)
            return self._phrases(part.get("text", ""))
        return self._phrases(json.loads(self.rec.PartialResult()).get("partial", ""))

    def sureness(self, phrase: str) -> float:
        """How sure the recognizer is of these words, the last time it heard them (this ends the utterance)."""
        self.parts.append(json.loads(self.rec.FinalResult()))
        want = next((h for h, p in self._back.items() if p == phrase), phrase).split()
        for part in reversed(self.parts):
            got = {w.get("word"): w.get("conf", 0.0) for w in part.get("result", [])}
            if want and all(w in got for w in want):
                return min(got[w] for w in want)
        return 0.0

    def result(self) -> tuple[str, float]:
        self.parts.append(json.loads(self.rec.FinalResult()))
        if any("alternatives" in p for p in self.parts):
            alts = self.alternatives()
            return (alts[0] if alts else ""), _likelier(self.parts)
        words = [w for p in self.parts for w in p.get("result", [])]
        text = " ".join(p.get("text", "") for p in self.parts).strip()
        text = " ".join(t for t in text.split() if t != "[unk]")
        conf = sum(w.get("conf", 0) for w in words) / len(words) if words else 0.0
        return self._phrases(text), conf

    def alternatives(self) -> list[str]:
        """The likely sentences, the best first, after `result()`: an utterance heard in several parts gives each
        alternative of one part with the best of the others."""
        alts = [p.get("alternatives") or [{"text": p.get("text", "")}] for p in self.parts]
        best = [a[0].get("text", "") for a in alts]
        out = []
        for i, part in enumerate(alts):
            for a in part:
                text = " ".join(t for t in best[:i] + [a.get("text", "")] + best[i + 1:] if t)
                if text:
                    out.append(text)
        return list(dict.fromkeys(out))


def _likelier(parts: list[dict]) -> float:
    """How sure the recognizer is of its best sentence, from the likelihoods of the alternatives (log values): the
    share of the best among them, for the least sure part with words."""
    sure = []
    for p in parts:
        alts = [a for a in p.get("alternatives", []) if "confidence" in a]
        if not alts or not alts[0].get("text"):
            continue
        top = alts[0]["confidence"]
        sure.append(1.0 / sum(math.exp(min(0.0, a["confidence"] - top)) for a in alts))
    return min(sure) if sure else 0.0
