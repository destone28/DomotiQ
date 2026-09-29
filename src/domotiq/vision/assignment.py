# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Minimum-cost assignment (Hungarian method) for small rectangular matrices.

The house never sees more than a few dozen things at once, so a plain
O(n^3) implementation is enough and saves a large dependency on the board.
"""

from __future__ import annotations

import numpy as np


def linear_sum_assignment(cost: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rows and columns of the optimal assignment, like scipy's function of the same name."""
    c = np.asarray(cost, dtype=np.float64)
    if c.size == 0:
        return np.array([], int), np.array([], int)
    transposed = c.shape[0] > c.shape[1]
    if transposed:
        c = c.T
    n, m = c.shape                       # n <= m
    big = float(np.abs(c[np.isfinite(c)]).max(initial=1.0)) * (n + 1) + 1.0
    c = np.where(np.isfinite(c), c, big)
    u = np.zeros(n + 1)
    v = np.zeros(m + 1)
    p = np.zeros(m + 1, dtype=int)       # p[j]: row assigned to column j (1-based, 0 = none)
    way = np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, np.inf)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            cur = c[i0 - 1] - u[i0] - v[1:]
            free = ~used[1:]
            better = free & (cur < minv[1:])
            minv[1:][better] = cur[better]
            way[1:][better] = j0
            cand = np.where(free, minv[1:], np.inf)
            j1 = int(np.argmin(cand)) + 1
            delta = cand[j1 - 1]
            used_idx = np.nonzero(used)[0]
            u[p[used_idx]] += delta
            v[used_idx] -= delta
            minv[1:][free] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    rows, cols = [], []
    for j in range(1, m + 1):
        if p[j]:
            rows.append(p[j] - 1)
            cols.append(j - 1)
    rows, cols = np.array(rows, int), np.array(cols, int)
    if transposed:
        rows, cols = cols, rows
    order = np.argsort(rows)
    return rows[order], cols[order]
