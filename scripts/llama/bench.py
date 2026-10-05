#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The matrix products of Qwen2.5-0.5B with two builds of llama.cpp, alternated, best of 3 runs each, and how much
their results differ.

    python3 scripts/llama/bench.py <mmbench of the build in use> <mmbench of the new build> <label>

(mmbench.c compiled against each build; 3 threads, as the domotiq-llm service.)"""
import subprocess
import sys

import numpy as np

BASE, NEW, LABEL = sys.argv[1], sys.argv[2], sys.argv[3]
SHAPES = [("q5_0", 4864, 896), ("q5_0", 896, 896), ("q5_0", 128, 896), ("q4_K", 896, 4864), ("q6_K", 896, 4864),
          ("q8_0", 128, 896), ("q8_0", 151936, 896)]


def best(binary, t, m, k, n, out):
    runs = 20 if n == 1 else 4
    ms = []
    for _ in range(3):
        line = subprocess.run([binary, t, str(m), str(k), str(n), "3", str(runs), out],
                              capture_output=True, text=True).stdout
        ms.append(float(line.split("best")[1].split("ms")[0]))
    return min(ms)


print(f"{'product':28s} {'base ms':>9s} {LABEL + ' ms':>11s} {'speed-up':>9s} {'max diff':>10s}")
for t, m, k in SHAPES:
    for n in ((1, 17, 64) if t == "q5_0" else (1, 64)):
        if m > 100000 and n > 1:
            continue
        a = best(BASE, t, m, k, n, "/tmp/a.bin")
        b = best(NEW, t, m, k, n, "/tmp/b.bin")
        ra, rb = np.fromfile("/tmp/a.bin", np.float32), np.fromfile("/tmp/b.bin", np.float32)
        diff = float(np.max(np.abs(ra - rb)) / max(np.max(np.abs(ra)), 1e-9))
        print(f"{t} {m}x{k} n={n:<3d}{'':8s} {a:9.3f} {b:11.3f} {a / b:8.2f}x {diff:10.1e}")
