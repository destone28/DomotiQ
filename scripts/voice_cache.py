#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Synthesize ahead of time every fixed sentence the house says, for its voice cache.

The house keeps on disk every sentence it synthesizes (var/voice/, see
src/domotiq/voice/tts.py), and also reads models/voice-cache/. This script
fills that folder with the fixed sentences, the ones with no name or number in
them, so that a house says them at once from its very first start:

    venv/bin/python scripts/voice_cache.py            on a board, with its own Piper (127.0.0.1:5010)
    python scripts/voice_cache.py --url URL           anywhere a Piper HTTP server answers
    python scripts/voice_cache.py --list              only print the sentences

The sentences are taken from the code itself: the frequent ones, every way of
saying something that has no blank to fill (voice/variants.py), the replies
written in both languages (reply("...", "...") and {"it": ..., "en": ...}) and
the answers chosen by language (answers.py). release.sh copies the folder from
the PC to the board.
"""

from __future__ import annotations

import argparse
import ast
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domotiq.voice import variants  # noqa: E402
from domotiq.voice.manager import FREQUENT  # noqa: E402
from domotiq.voice.tts import URL, Speaker, normalize  # noqa: E402

SOURCES = ["src/domotiq/voice/*.py", "src/domotiq/activities.py", "src/domotiq/default_rules.py"]


def _fixed(text: object) -> bool:
    """A whole sentence with no blank to fill (not a pattern of words, not a piece of a sentence)."""
    return (isinstance(text, str) and bool(text.strip()) and text[0].isupper() and len(text) <= 300
            and not any(c in text for c in "{|()[]\\"))


def _pairs_in_code(path: Path) -> list[tuple[str, str]]:
    """(Italian, English) written as constants: reply("...", "..."), {"it": "...", "en": "..."} and
    ("..." if lang == "it" else "...")."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            args = node.args
            if name == "reply" and len(args) >= 2 and all(isinstance(a, ast.Constant) for a in args[:2]):
                out.append((args[0].value, args[1].value))
        elif isinstance(node, ast.Dict):
            keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
            if sorted(k for k in keys if k) == ["en", "it"] and all(isinstance(v, ast.Constant) for v in node.values):
                values = dict(zip(keys, (v.value for v in node.values)))
                out.append((values["it"], values["en"]))
        elif isinstance(node, ast.IfExp) and isinstance(node.body, ast.Constant) and isinstance(node.orelse, ast.Constant):
            test = ast.unparse(node.test).replace(" ", "")
            if test in ('lang=="it"', 'self.lang=="it"', 'it'):
                out.append((node.body.value, node.orelse.value))
    return [(it, en) for it, en in out if _fixed(it) and _fixed(en)]


def sentences() -> list[tuple[str, str]]:
    """Every fixed sentence, as (language, text), each once."""
    found: list[tuple[str, str]] = []
    for lang, lines in FREQUENT.items():
        found += [(lang, line) for line in lines]
    for value in vars(variants).values():
        if isinstance(value, list) and value and all(isinstance(v, tuple) and len(v) == 2 for v in value):
            for it, en in value:
                if _fixed(it) and _fixed(en):
                    found += [("it", it), ("en", en)]
    for pattern in SOURCES:
        for path in sorted(ROOT.glob(pattern)):
            for it, en in _pairs_in_code(path):
                found += [("it", it), ("en", en)]
    seen, out = set(), []
    for lang, text in found:
        key = (lang, normalize(text, lang))
        if key[1] and key not in seen:
            seen.add(key)
            out.append((lang, text))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=URL, help="the Piper HTTP server (default %(default)s)")
    ap.add_argument("--out", default=str(ROOT / "models" / "voice-cache"), help="the folder to fill")
    ap.add_argument("--list", action="store_true", help="only print the sentences")
    args = ap.parse_args()
    todo = sentences()
    if args.list:
        for lang, text in todo:
            print(f"{lang}\t{text}")
        print(f"{len(todo)} sentences", file=sys.stderr)
        return 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    speaker = Speaker(url=args.url, cache_dir=out, disk_max=100000)
    made = kept = failed = 0
    start = time.monotonic()
    for k, (lang, text) in enumerate(todo, 1):
        line = normalize(text, lang)
        f = speaker._file(lang, line)
        if f is not None and f.exists():
            kept += 1
            continue
        try:
            speaker._synth(line, lang)
            made += 1
        except Exception as e:  # noqa: BLE001 - one sentence that fails does not stop the others
            failed += 1
            print(f"failed: {lang} {text!r}: {e}", file=sys.stderr)
        if k % 25 == 0:
            print(f"{k}/{len(todo)}", file=sys.stderr)
    print(f"{made} synthesized, {kept} already there, {failed} failed, in {time.monotonic() - start:.0f} s: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
