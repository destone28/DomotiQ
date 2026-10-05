#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The whole model with two builds of the CPU library of llama.cpp: the same llama-bench, the library taken from
LD_LIBRARY_PATH (which wins over the RUNPATH of the binary), alternated test by test, median of 3 rounds.

    python3 scripts/llama/ab_bench.py <llama-bench> <build/bin of the original> <build/bin of the new one> [model]

(3 threads, as the domotiq-llm service.) The results go to ab_bench.json."""
import csv
import io
import json
import os
import statistics
import subprocess
import sys

BENCH = sys.argv[1]
LIBS = {"original": sys.argv[2], "new": sys.argv[3]}
MODEL = sys.argv[4] if len(sys.argv) > 4 else os.path.expanduser(
    "~/domotiq/models/llm/qwen2.5-0.5b-instruct-q4_k_m.gguf")
TESTS = [("-p 16 -n 0 -d 0 -fa 1", "read 16, no context"), ("-p 0 -n 8 -d 0 -fa 1", "write 8, no context"),
         ("-p 16 -n 0 -d 1400 -fa 0", "read 16, 1400 of context, fa off"),
         ("-p 0 -n 8 -d 1400 -fa 0", "write 8, 1400 of context, fa off")]
ROUNDS = 3

res = {(t, lib): [] for t, _ in TESTS for lib in LIBS}
for r in range(ROUNDS):
    for t, label in TESTS:
        for lib, path in (LIBS.items() if r % 2 == 0 else reversed(list(LIBS.items()))):
            env = dict(os.environ, LD_LIBRARY_PATH=path)
            out = subprocess.run([BENCH, "-m", MODEL, "-t", "3", "-r", "1", "-o", "csv", *t.split()],
                                 capture_output=True, text=True, env=env).stdout
            for row in csv.DictReader(io.StringIO(out)):
                res[(t, lib)].append(float(row["avg_ts"]))
            print(r, label, lib, res[(t, lib)][-1:], flush=True)
summary = []
for t, label in TESTS:
    o, n = statistics.median(res[(t, "original")]), statistics.median(res[(t, "new")])
    summary.append({"test": label, "original": round(o, 2), "new": round(n, 2), "ratio": round(n / o, 2),
                    "original_runs": res[(t, "original")], "new_runs": res[(t, "new")]})
    print(f"{label}: original {o:.2f} t/s, new {n:.2f} t/s, {n / o:.2f}x", flush=True)
json.dump(summary, open("ab_bench.json", "w"), indent=1)
print("done", flush=True)
