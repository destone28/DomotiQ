#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""How well the house understands what is said to it: the sentences of the house, said by Piper voices (clean, in a
small room, far away with noise), heard by the Vosk models with the code of the house, understood by its rules.

    python3 scripts/stt_bench.py decode --models DIR --voices DIR [--langs it,en] [--out stt_bench.json]
    python3 scripts/stt_bench.py score stt_bench.json --mode new
    PYTHONPATH=<src of another version> python3 scripts/stt_bench.py score stt_bench.json --mode old

`decode` needs vosk, piper-tts and numpy (a PC is much faster than the board); DIR of the models has vosk/ with the
small models, DIR of the voices the Piper .onnx files. Every clip is heard four ways: freely, freely with
alternatives, by the list of names as it was (the names the model does not know left out) and as it is now (heard
with a spelling the model knows). `score` compares what the rules understand from each recognition with what they
understand from the sentence itself: "old" is the house before the alternatives (free recognition, then the names of
the list when the sentence means nothing), "new" the house now (VoiceManager.handle: the alternatives, the list also
for a name the house does not know, whole names only). The context of a conversation and the language model are left
out. The clips go to a cache next to the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not os.environ.get("PYTHONPATH"):
    sys.path.insert(0, str(ROOT / "src"))

RATE = 16000
VOICES = {"it": ["it_IT-serena-medium", "it_IT-paola-medium", "it_IT-riccardo-x_low"],
          "en": ["en_US-ljspeech-medium", "en_US-ryan-medium", "en_GB-alan-medium"]}
SPEEDS = (1.0, 1.15)
# reverberation time (s), signal to noise ratio (dB), level
CONDITIONS = {"clean": None, "room": (0.35, 18, 0.35), "far": (0.6, 9, 0.2)}
NAMES = ["Mister Brown", "Mr Brown", "Viola", "Violet", "Rossana", "Honda Civic", "Mister Green", "Mister Blu",
         "Rossellina", "Giallo Galli"]                                   # the characters of a house
GROUPS = {
    "it": {
        "commands": [
            "accendi la luce in cucina", "accendi la luce in bagno di colore verde",
            "accendi la luce rossa in soggiorno", "spegni la luce nel bagno", "spegni tutte le luci",
            "spegni la luce in camera da letto", "accendi la luce blu in giardino", "chi c'è in cucina",
            "chi c'è in soggiorno", "chi c'è in camera da letto", "c'è qualcuno in giardino",
            "quante persone ci sono in casa", "quanti animali ci sono", "quanti gradi ci sono in cucina",
            "che temperatura c'è in bagno", "com'è l'umidità in bagno", "la cucina è vuota", "dov'è la macchina",
            "che ore sono", "facciamo festa", "accendi il barbecue", "facciamo una grigliata", "guardiamo un film",
            "buonanotte", "buongiorno", "stiamo uscendo", "raccontami una storia", "raccontami una barzelletta",
            "come ti chiami", "cosa sai fare", "parla inglese", "alza il volume", "abbassa il volume",
            "com'è la casa", "chi sono i personaggi che conosci", "annulla", "metti la luce gialla in cucina",
            "accendi la luce del garage", "c'è gente in soggiorno"],
        "names": [
            "dov'è Viola", "dov'è Rossana", "dov'è Mister Brown", "dov'è Mister Green", "dov'è Mister Blu",
            "dov'è Rossellina", "dov'è Giallo Galli", "dov'è Honda Civic", "dove si trova Rossellina",
            "cosa sai di Viola", "chi è Mister Green", "parlami di Giallo Galli", "raccontami qualcosa di Rossellina",
            "accendi la luce preferita di Viola", "accendi la luce del colore preferito di Rossana",
            "Mister Brown e Rossellina stanno insieme", "Viola e Rossana sono insieme", "cosa ha fatto Mister Blu",
            "dov'è stata Viola", "raccontami una storia su Giallo Galli", "cosa mangia Rossellina",
            "che lavoro fa Mister Green", "ricorda che Viola fa la ballerina", "dove vuole andare Rossellina",
            "qual è il colore preferito di Rossana", "che musica piace a Mister Brown"],
        "alone": ["Viola", "Rossellina", "Mister Brown", "Giallo Galli", "Honda Civic", "sì", "no", "va bene"],
        "not commands": [
            "che tempo farà domani", "quanti anni hai", "mi piace molto questa casa",
            "qual è la capitale della francia", "oggi sono andato al mare", "che bella giornata", "ho fame",
            "come stai", "quanto costa questa casa", "chi ha costruito questa casa"],
    },
    "en": {
        "commands": [
            "turn on the light in the kitchen", "turn off the bathroom light", "who is in the living room",
            "where is Violet", "where is Mister Brown", "where is Rossellina", "how many people are in the house",
            "what time is it", "let's party", "tell me a story", "what is the temperature in the kitchen",
            "make the bedroom light blue", "good night", "what do you know about Mister Green", "speak italian",
            "is anyone in the garden", "where is the car", "turn on the red light in the living room",
            "where is Giallo Galli", "who are you"],
        "not commands": ["what's the weather like tomorrow", "how old are you", "i really like this house",
                         "i'm hungry"],
    },
}


# ---------------------------------------------------------------------------------------------------------- decode
def synth(text, voice, speed, voices, cache, _loaded={}):
    import numpy as np
    key = hashlib.md5(f"{voice}|{text}|{speed}".encode()).hexdigest()
    path = cache / f"{key}.npy"
    if path.exists():
        return np.load(path)
    from piper import PiperVoice, SynthesisConfig
    if voice not in _loaded:
        _loaded[voice] = PiperVoice.load(str(Path(voices) / f"{voice}.onnx"))
    chunks = list(_loaded[voice].synthesize(text, syn_config=SynthesisConfig(length_scale=speed)))
    x = np.concatenate([np.frombuffer(c.audio_int16_bytes, dtype="<i2").astype(np.float32) / 32768 for c in chunks])
    n = int(len(x) * RATE / chunks[0].sample_rate)
    y = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    pad = np.zeros(int(RATE * 0.3), np.float32)
    out = np.concatenate([pad, y, pad])
    np.save(path, out)
    return out


def room(x, rt60, snr_db, seed, gain):
    """A small room (decaying noise as impulse response), a microphone that cuts the low and high ends, background
    noise at the given SNR, and a lower level."""
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int(RATE * rt60)
    ir = rng.normal(0, 1, n) * np.exp(-6.9 * np.arange(n) / RATE / rt60)
    ir[0] = 6.0                                     # the direct sound
    ir /= np.sqrt(np.sum(ir ** 2))
    y = np.convolve(x, ir)[: len(x) + n // 2]
    f = np.fft.rfftfreq(len(y), 1 / RATE)
    spec = np.fft.rfft(y) / np.sqrt(1 + (150 / np.maximum(f, 1)) ** 4) / np.sqrt(1 + (f / 5500) ** 8)
    y = np.fft.irfft(spec, len(y))
    pink = np.fft.irfft(np.fft.rfft(rng.normal(0, 1, len(y))) / np.sqrt(np.maximum(f, 20)), len(y))
    p = max(np.mean(y ** 2), 1e-9)
    y = y + pink * np.sqrt(p / 10 ** (snr_db / 10) / max(np.mean(pink ** 2), 1e-12))
    return (y * gain).astype(np.float32)


_job: dict = {}


def _init(models, voices, cache):
    import vosk
    vosk.SetLogLevel(-1)
    from domotiq.voice.stt import Listener
    _job.update(listener=Listener(Path(models)), voices=voices, cache=Path(cache))


def _hear(listener, pcm, lang, grammar=None, respell=True, alternatives=0):
    s = listener.session(lang, grammar, respell, alternatives)
    for i in range(0, len(pcm), 3200):
        s.feed(pcm[i:i + 3200])
    text, conf = s.result()
    return (text, round(conf, 3), s.alternatives()) if alternatives else (text, round(conf, 3))


def _decode(clip):
    import numpy as np
    lang, group, text, voice, speed, cond = clip
    x = synth(text, voice, speed, _job["voices"], _job["cache"])
    if CONDITIONS[cond] is not None:
        seed = int(hashlib.md5(f"{text}{voice}{speed}{cond}".encode()).hexdigest()[:8], 16)
        x = room(x, *CONDITIONS[cond][:2], seed, CONDITIONS[cond][2])
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    li = _job["listener"]
    names = [n.lower() for n in NAMES]
    best, conf, alts = _hear(li, pcm, lang, alternatives=5)
    return {"lang": lang, "group": group, "text": text, "voice": voice, "speed": speed, "cond": cond,
            "free": _hear(li, pcm, lang)[0], "best": best, "alternatives": alts,
            "names_old": _hear(li, pcm, lang, names, respell=False)[0], "names_new": _hear(li, pcm, lang, names)[0]}


def decode(args):
    out = Path(args.out)
    cache = out.with_suffix("").parent / (out.stem + "-clips")
    cache.mkdir(parents=True, exist_ok=True)
    clips = [(lang, group, text, voice, speed, cond) for lang in args.langs.split(",")
             for group, texts in GROUPS[lang].items() for text in texts for voice in VOICES[lang]
             for speed in SPEEDS for cond in CONDITIONS]
    for lang, _, text, voice, speed, _ in clips:            # Piper once, in this process
        synth(text, voice, speed, args.voices, cache)
    with Pool(args.procs, initializer=_init, initargs=(args.models, args.voices, str(cache))) as pool:
        rows = pool.map(_decode, clips, chunksize=4)
    out.write_text(json.dumps(rows, ensure_ascii=False))
    print(f"{len(rows)} clips -> {out}")


# ----------------------------------------------------------------------------------------------------------- score
def score(args):
    from domotiq.voice import intents
    from domotiq.voice.intents import Intent, find_names, normalize, parse
    rows = json.loads(Path(args.file).read_text())

    def key(intent):
        return None if intent is None else (
            intent.name, json.dumps({k: v for k, v in intent.args.items() if k not in ("text", "topic")},
                                    sort_keys=True))

    def unknown(intent):
        return intent is not None and intent.name == "where_is" and intent.args.get("name") not in NAMES

    def by_list(text, intent, heard, names_of):
        """The names the list heard, for a sentence that names nobody (as VoiceManager.handle)."""
        who = names_of(normalize(heard), NAMES) if heard else []
        if not who or find_names(normalize(text), NAMES):
            return intent
        if re.search(r"\b(dov\w*|dove|where|cerca|trova|find)\b", normalize(text)):
            return Intent("where_is", {"name": who[0]}, 0.7)
        return parse(f"{text} {who[0]}", NAMES) or intent

    def old(r):
        intent = parse(r["free"], NAMES)
        return by_list(r["free"], intent, r["names_old"], find_names) if intent is None else intent

    def new(r):
        text, intent = r["best"], parse(r["best"], NAMES)
        for alt in r["alternatives"][1:]:
            if intent is not None and not unknown(intent):
                break
            other = parse(alt, NAMES)
            if other is not None and not unknown(other):
                text, intent = alt, other
        if intent is None or unknown(intent):
            intent = by_list(text, intent, r["names_new"], intents.whole_names)
        return intent

    understand = old if args.mode == "old" else new
    tot = defaultdict(lambda: [0, 0])
    taken = defaultdict(lambda: [0, 0])          # sentences that are no command, taken for one all the same
    for r in rows:
        got = understand(r)
        ok = key(got) == key(parse(r["text"], NAMES))
        for k in ((r["lang"], r["group"]), (r["lang"], r["cond"]), (r["lang"], "all")):
            tot[k][0] += ok
            tot[k][1] += 1
        if r["group"] == "not commands":
            taken[r["lang"]][0] += got is not None
            taken[r["lang"]][1] += 1
    print(f"mode {args.mode}: understood as from the sentence itself")
    for lang in dict.fromkeys(r["lang"] for r in rows):
        cols = list(GROUPS[lang]) + list(CONDITIONS) + ["all"]
        print(f"  {lang}: " + "  ".join(f"{c} {100 * tot[(lang, c)][0] / max(1, tot[(lang, c)][1]):.1f}% "
                                         f"({tot[(lang, c)][0]}/{tot[(lang, c)][1]})" for c in cols))
        n, of = taken[lang]
        print(f"  {lang}: not commands taken for a command {100 * n / max(1, of):.1f}% ({n}/{of})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decode")
    d.add_argument("--models", required=True, help="folder with vosk/ inside")
    d.add_argument("--voices", required=True, help="folder with the Piper voices (.onnx)")
    d.add_argument("--langs", default="it,en")
    d.add_argument("--out", default="stt_bench.json")
    d.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    s = sub.add_parser("score")
    s.add_argument("file")
    s.add_argument("--mode", choices=("old", "new"), default="new")
    args = ap.parse_args()
    decode(args) if args.cmd == "decode" else score(args)


if __name__ == "__main__":
    main()
