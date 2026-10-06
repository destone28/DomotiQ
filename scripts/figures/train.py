#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""A small classifier of the crops of the figurines: each character of the house, or "niente".

    python scripts/figures/train.py <out dir> <crops dir> [more crops dirs] [--epochs N] [--folds K] [--only k]
                                    [--drop suspect.json]

Needs PyTorch and onnx on the PC (not on the board). The out dir gets figures.onnx and figures.json, to be copied to
models/vision/ on the board; suspect.json lists the crops whose label the final model strongly doubts (the house was
probably wrong there): a second run with --drop leaves them out.

Validation is by blocks of time: the crops of each class are sorted by time and split into K blocks; block k is
left out while training on the others (frames next to each other are almost the same picture, a random split would
measure nothing). Then the final model is trained on everything and exported to ONNX for onnxruntime.
Light, shadow, white balance, rotation and blur are varied while training: the house sees the figurines from above,
turned any way, under the hall light, its own coloured lights and the shadows of the visitors.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

SIZE = 48               # the crops (made at 64) are seen at this size: enough for a figurine, half the work
MIN_SAMPLES = 20


# ------------------------------------------------------------------ data
def load(dirs: list[Path]) -> list[dict]:
    items = []
    for d in dirs:
        for e in json.loads((d / "index.json").read_text()):
            e = dict(e, path=str(d / e["file"]))
            items.append(e)
    return items


def augment(img: np.ndarray, rng: random.Random) -> np.ndarray:
    h, w = img.shape[:2]
    # turned any way, a little bigger or smaller, a little off centre
    angle = rng.uniform(0, 360)
    scale = rng.uniform(0.85, 1.15)
    m = cv2.getRotationMatrix2D((w / 2 + rng.uniform(-4, 4), h / 2 + rng.uniform(-4, 4)), angle, scale)
    img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    if rng.random() < 0.5:
        img = img[:, ::-1]
    f = img.astype(np.float32)
    # the hall light and the webcam: brightness, contrast, gamma, white balance
    f *= rng.uniform(0.45, 1.5)
    mean = f.mean()
    f = (f - mean) * rng.uniform(0.7, 1.3) + mean
    f *= np.array([rng.uniform(0.85, 1.15) for _ in range(3)], np.float32)
    f = np.clip(f, 0, 255)
    f = 255.0 * (f / 255.0) ** rng.uniform(0.7, 1.5)
    # a shadow across part of it, or the coloured light of a room
    if rng.random() < 0.5:
        a = rng.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        t = ((xx - w / 2) * math.cos(a) + (yy - h / 2) * math.sin(a)) / (0.5 * max(w, h))
        low = rng.uniform(0.35, 0.9)
        edge = rng.uniform(-0.6, 0.6)
        mask = np.clip((t - edge) * rng.uniform(1.5, 6.0) + 0.5, 0, 1)
        f *= (low + (1 - low) * mask)[..., None]
    if rng.random() < 0.25:
        tint = np.array([rng.uniform(0.7, 1.3) for _ in range(3)], np.float32)
        f *= tint
    f = np.clip(f, 0, 255)
    if rng.random() < 0.3:
        f = cv2.GaussianBlur(f, (3, 3), rng.uniform(0.3, 1.2))
    if rng.random() < 0.5:
        f += np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(1, 6), f.shape).astype(np.float32)
    img = np.clip(f, 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, rng.randrange(55, 95)])
        img = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return img


def tensor(imgs: list[np.ndarray]) -> torch.Tensor:
    imgs = [im if im.shape[0] == SIZE else cv2.resize(im, (SIZE, SIZE), interpolation=cv2.INTER_AREA) for im in imgs]
    x = np.stack(imgs).astype(np.float32)[..., ::-1] / 255.0           # BGR -> RGB
    x = (x - 0.5) / 0.25
    return torch.from_numpy(np.ascontiguousarray(x.transpose(0, 3, 1, 2)))


# ------------------------------------------------------------------ model
class FigureNet(nn.Module):
    """Four convolution blocks and a linear layer, some 190 thousand weights. The first two blocks, on the bigger
    pictures, have one convolution only: they cost most (on the board some 10 ms a crop on one thread, 6 on two)."""

    def __init__(self, classes: int) -> None:
        super().__init__()
        chans = [3, 16, 32, 64, 96]
        layers = []
        for i, (a, b) in enumerate(zip(chans, chans[1:])):
            layers += [nn.Conv2d(a, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True)]
            if i >= 2:
                layers += [nn.Conv2d(b, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True)]
            layers.append(nn.MaxPool2d(2))
        self.features = nn.Sequential(*layers)
        self.drop = nn.Dropout(0.3)
        self.head = nn.Linear(chans[-1], classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = x.mean(dim=(2, 3))
        return self.head(self.drop(x))


# ------------------------------------------------------------------ training
def train(train_items, classes, epochs, seed, log_every=5, steps=60):
    rng = random.Random(seed)
    torch.manual_seed(seed)
    idx = {c: i for i, c in enumerate(classes)}
    imgs = [cv2.imread(e["path"]) for e in train_items]
    ys = np.array([idx[e["label"]] for e in train_items])
    counts = Counter(ys.tolist())
    weights = torch.tensor([1.0 / math.sqrt(counts.get(i, 1)) for i in range(len(classes))], dtype=torch.float32)
    weights *= len(classes) / weights.sum()
    # every class seen about as often in each epoch
    per_sample = np.array([1.0 / counts[y] for y in ys])
    per_sample /= per_sample.sum()
    model = FigureNet(len(classes))
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-3)
    steps_per_epoch = steps
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=epochs * steps_per_epoch)
    np_rng = np.random.default_rng(seed)
    for epoch in range(epochs):
        model.train()
        total, seen = 0.0, 0
        for _ in range(steps_per_epoch):
            batch = np_rng.choice(len(imgs), size=128, p=per_sample)
            x = tensor([augment(imgs[i], rng) for i in batch])
            y = torch.from_numpy(ys[batch])
            loss = F.cross_entropy(model(x), y, weight=weights, label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(batch)
            seen += len(batch)
        if (epoch + 1) % log_every == 0 or epoch == epochs - 1:
            print(f"  epoch {epoch + 1}/{epochs} loss {total / seen:.3f}", flush=True)
    return model


@torch.no_grad()
def predict(model, items):
    model.eval()
    out = []
    for i in range(0, len(items), 256):
        x = tensor([cv2.imread(e["path"]) for e in items[i:i + 256]])
        out.append(F.softmax(model(x), dim=1).numpy())
    return np.concatenate(out) if out else np.zeros((0, 0))


def blocks(items, classes, k, fold):
    """Train and validation sets: for each class, its crops in time order, block `fold` of `k` left out."""
    tr, va = [], []
    for c in classes:
        mine = sorted((e for e in items if e["label"] == c), key=lambda e: (e["rec"], e["frame"]))
        n = len(mine)
        lo, hi = n * fold // k, n * (fold + 1) // k
        va += mine[lo:hi]
        tr += mine[:lo] + mine[hi:]
    return tr, va


def report(probs, items, classes):
    idx = {c: i for i, c in enumerate(classes)}
    y = np.array([idx[e["label"]] for e in items])
    p = probs.argmax(1)
    conf = np.zeros((len(classes), len(classes)), int)
    for a, b in zip(y, p):
        conf[a, b] += 1
    acc = float((p == y).mean()) if len(y) else 0.0
    per = {c: (float(conf[i, i] / conf[i].sum()) if conf[i].sum() else None) for i, c in enumerate(classes)}
    return acc, per, conf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("crops", type=Path, nargs="+")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--only", type=int, nargs="*", default=None, help="the blocks of time to leave out, one at a time")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--steps", type=int, default=60, help="batches of 128 per epoch")
    ap.add_argument("--drop", type=Path, default=None, help="json list of crop files to leave out (labels found wrong)")
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    items = load(args.crops)
    if args.drop:
        dropped = set(json.loads(args.drop.read_text()))
        items = [e for e in items if e["file"] not in dropped]
        print(f"left out {len(dropped)} crops whose labels were found wrong")
    counts = Counter(e["label"] for e in items)
    classes = sorted(c for c, n in counts.items() if n >= MIN_SAMPLES and c != "niente") + ["niente"]
    items = [e for e in items if e["label"] in classes]
    print("classes:", {c: counts[c] for c in classes}, "| left out:",
          {c: n for c, n in counts.items() if c not in classes})
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for fold in (args.only if args.only is not None else range(args.folds)):
        tr, va = blocks(items, classes, args.folds, fold)
        t0 = time.time()
        model = train(tr, classes, args.epochs, seed=fold, log_every=args.epochs, steps=args.steps)
        probs = predict(model, va)
        acc, per, conf = report(probs, va, classes)
        # how sure it is when it is right and when it is wrong: the threshold for a "second opinion"
        idx = {c: i for i, c in enumerate(classes)}
        y = np.array([idx[e["label"]] for e in va])
        top = probs.max(1)
        right = probs.argmax(1) == y
        sure = top >= 0.9
        print(f"fold {fold + 1}/{args.folds}: {len(tr)} train, {len(va)} validation, accuracy {acc:.3f} "
              f"({time.time() - t0:.0f} s); sure (>=0.9) on {sure.mean():.2f} of them, right when sure "
              f"{(right & sure).sum() / max(sure.sum(), 1):.3f}", flush=True)
        print("   per class:", {c: (round(v, 2) if v is not None else None) for c, v in per.items()})
        (args.out / f"val_{fold}.json").write_text(json.dumps(
            [{"file": e["file"], "label": e["label"], "p": [round(float(v), 4) for v in pr]} for e, pr in zip(va, probs)]))
        results.append({"fold": fold, "accuracy": acc, "per_class": per, "confusion": conf.tolist(),
                        "sure_share": float(sure.mean()), "right_when_sure": float((right & sure).sum() / max(sure.sum(), 1))})
    (args.out / "folds.json").write_text(json.dumps({"classes": classes, "folds": results}, indent=1))
    print("mean accuracy over the blocks:", round(float(np.mean([r["accuracy"] for r in results])), 3))
    model = train(items, classes, args.epochs, seed=99, steps=args.steps)
    # the crops the final model is sure are something else than their label: most likely the house was wrong there
    probs = predict(model, items)
    idx = {c: i for i, c in enumerate(classes)}
    suspect = [e["file"] for e, p in zip(items, probs) if p[idx[e["label"]]] < 0.05 and p.max() > 0.95]
    (args.out / "suspect.json").write_text(json.dumps(suspect))
    print(f"crops whose label the model doubts strongly: {len(suspect)}", dict(Counter(
        next(e["label"] for e in items if e["file"] == f) for f in suspect[:2000])))
    model.eval()
    dummy = torch.zeros(1, 3, SIZE, SIZE)
    onnx_path = args.out / "figures.onnx"
    torch.onnx.export(model, dummy, str(onnx_path), input_names=["crops"], output_names=["logits"],
                      dynamic_axes={"crops": {0: "n"}, "logits": {0: "n"}}, opset_version=17, dynamo=False)
    meta = {"classes": classes, "size": SIZE, "margin": 0.35, "mean": 0.5, "std": 0.25, "rgb": True,
            "trained": time.strftime("%Y-%m-%d %H:%M"), "samples": {c: counts[c] for c in classes}}
    (args.out / "figures.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print("exported:", onnx_path, onnx_path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
