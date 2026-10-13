#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The requests of the house to a llama-server started apart (a build and its options), as the house sends them.

    python3 e2e.py <label> <llama-server> <port> [server options...]

The server gets the instructions of the commands first (as at a start of the house), then sentences a house
really sent to the model; prompt and generation times come from the server itself. The results go to
e2e-<label>.json."""
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.request

LABEL, SERVER, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
OPTIONS = sys.argv[4:]
HOME = os.path.expanduser("~")
MODEL = f"{HOME}/domotiq/models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
URL = f"http://127.0.0.1:{PORT}"
sys.path.insert(0, f"{HOME}/domotiq/src")
from domotiq.voice import llm  # noqa: E402

idents = json.load(open(f"{HOME}/domotiq/var/config/identities.json"))
idents = idents if isinstance(idents, list) else idents.get("identities", list(idents.values()))
names = [i["name"] for i in idents] + [i["alias_en"] for i in idents if i.get("alias_en")]
SENTENCES = ["la cucina è vuota", "always in the living room", "what is rose", "che meteo ci sarà tradate domani",
             "diminuita del bagno", "meglio chiamare sana undici quattordici", "for java so", "giusto si no si",
             "blu giusto", "enzo giorno"]


def ask(sentence, timeout=1200):
    body = {"messages": llm.messages(sentence, names), "temperature": 0, "max_tokens": 12, "cache_prompt": True,
            "grammar": llm.grammar(names), "logprobs": True, "top_logprobs": 1, "id_slot": 0}
    req = urllib.request.Request(URL + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return time.monotonic() - t0, out


proc = subprocess.Popen([SERVER, "-m", MODEL, "--host", "127.0.0.1", "--port", str(PORT), "-np", "1", "-c", "4096",
                         *OPTIONS], stdout=subprocess.DEVNULL, stderr=open(f"e2e-{LABEL}.log", "w"))
try:
    for _ in range(120):
        try:
            with urllib.request.urlopen(URL + "/health", timeout=2) as r:
                if r.status == 200:
                    break
        except OSError:
            pass
        time.sleep(1)
    wall, out = ask("ciao")                        # the instructions go into the cache, as at a start
    tm = out.get("timings", {})
    print(f"instructions: {tm.get('prompt_n')} tokens in {tm.get('prompt_ms', 0) / 1000:.1f} s "
          f"({tm.get('prompt_per_second', 0):.2f} tokens/s)")
    rows = []
    for sentence in SENTENCES:
        wall, out = ask(sentence)
        tm = out.get("timings", {})
        answer = out["choices"][0]["message"]["content"]
        print(f"{wall:6.2f} s  prompt {tm.get('prompt_n')} tok {tm.get('prompt_ms', 0):7.0f} ms  "
              f"generated {tm.get('predicted_n')} tok {tm.get('predicted_ms', 0):6.0f} ms  {sentence!r} -> {answer!r}")
        rows.append({"sentence": sentence, "answer": answer, "wall_s": wall,
                     **{k: tm.get(k) for k in ("prompt_n", "prompt_ms", "predicted_n", "predicted_ms")}})
    walls = [r["wall_s"] for r in rows]
    print(f"{LABEL}: median {statistics.median(walls):.2f} s, mean {statistics.mean(walls):.2f} s")
    json.dump({"label": LABEL, "options": OPTIONS, "requests": rows}, open(f"e2e-{LABEL}.json", "w"), indent=1)
finally:
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=30)
