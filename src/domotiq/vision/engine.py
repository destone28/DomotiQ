# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Everything between a frame and the tracks, without the camera.

The worker process feeds it the frames of the webcam; the tests feed it
synthetic ones. It owns the calibration, the empty-house reference, the
tracker, the privacy filter, the staff captures and the recordings.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from ..layout import Layout
from ..model import CATEGORY_NAMES, Identity, Track
from .geometry import Calibration
from .pipeline import Observation, Segmenter
from .privacy import Privacy
from .scene import StaticScene
from .signature import SIG_LEN, distance, signature, to_hex
from .tracker import ID_ACCEPT, Tracker

log = logging.getLogger(__name__)

ANALYSIS = (640, 480)
EMPTY_FRAMES = 20
COCO_CLASSES = ["person", "dog", "cat", "animal", "car", "object"]


class Engine:
    def __init__(self, layout: Layout, calib_dir: Path, dataset_dir: Path, recordings_dir: Path,
                 grab: Callable[[int], list[np.ndarray]] | None = None) -> None:
        self.layout = layout
        self.dir = calib_dir
        self.dataset_dir = dataset_dir
        self.recordings_dir = recordings_dir
        self.grab = grab                           # returns n new frames, for the staff commands
        for d in (calib_dir, dataset_dir, recordings_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.calib: Calibration | None = None
        self.segmenter: Segmenter | None = None
        self.tracker: Tracker | None = None
        self.privacy: Privacy | None = None
        self.identities: list[Identity] = []
        self.frame: np.ndarray | None = None        # the last frame, at analysis size
        self.frame_at = 0.0
        self.observations: list[Observation] = []
        self.tracks: list[Track] = []
        self.fps = 0.0
        self.proc_ms = 0.0
        self.on_question: Callable[[Track, list[str]], None] | None = None
        self._record: dict[str, Any] | None = None
        self._last_ref_update = 0.0
        self._moved = {"checked": 0.0, "shift": 0.0, "count": 0}
        self._background: dict[str, np.ndarray] = {}
        self._flooded_since = 0.0
        # before the calibration the house does not know where the bathroom is: it assumes the
        # camera is mounted as in the model, with a wide margin
        self._nominal_privacy = Privacy(layout, Calibration.synthetic(*ANALYSIS, layout.camera), margin_mm=45.0)
        self.load()

    # ------------------------------------------------------------ calibration and reference
    @property
    def calibrated(self) -> bool:
        return self.calib is not None and self.segmenter is not None

    @property
    def ready(self) -> bool:
        return self.calibrated and self.segmenter.reference is not None

    def load(self) -> None:
        calib = Calibration.load(self.dir / "calibration.json")
        if calib and calib.valid:
            self._setup(calib.scaled(*ANALYSIS) if (calib.width, calib.height) != ANALYSIS else calib)
            ref = cv2.imread(str(self.dir / "reference.png"))
            if ref is not None and ref.shape[1::-1] == ANALYSIS:
                self.segmenter.set_reference([ref])
                self._backgrounds()

    def _setup(self, calib: Calibration) -> None:
        self.calib = calib
        self.segmenter = Segmenter(self.layout, calib)
        tracker = Tracker(self.layout, calib)
        tracker.set_identities(self.identities)
        tracker.on_question = self._question
        self.tracker = tracker
        self.privacy = Privacy(self.layout, calib)

    def _question(self, vt, candidates: list[str]) -> None:
        if self.on_question is not None:
            self.on_question(vt.to_track(self.layout, self.tracker._rooms.get(vt.id)), candidates)

    def set_identities(self, identities: list[Identity]) -> None:
        self.identities = identities
        if self.tracker:
            self.tracker.set_identities(identities)

    def _backgrounds(self) -> None:
        """Colours of the floor, walls and lawns: a figurine too close to them is hard to see."""
        seg = self.segmenter
        lab = seg.reference
        scene = seg.scene
        self._background = {}
        free_floor = (scene.z < 0.5) & (seg.mask > 0)
        lawn = np.zeros(free_floor.shape, np.uint8)
        for r in self.layout.raw.get("lawns", []):
            cv2.fillPoly(lawn, [np.round(self.calib.rect_polygon(r)).astype(np.int32)], 255)
        groups = {
            "floor": free_floor & (lawn == 0),
            "lawn": free_floor & (lawn > 0),
            "wall": scene.kind == StaticScene.KINDS["wall"],
        }
        for name, m in groups.items():
            px = lab[m]
            if len(px) > 50:
                self._background[name] = signature(px[:: max(1, len(px) // 5000)])

    def set_corners(self, points: list[list[float]]) -> dict[str, Any]:
        if len(points) != 4:
            return {"ok": False, "error": "four corners are needed"}
        calib = Calibration.from_corners(points, ANALYSIS[0], ANALYSIS[1], self.layout.camera)
        # a sanity check: the base must come out as a convex shape of sensible size
        quad = np.array(calib.corners, np.float32)
        if not cv2.isContourConvex(quad) or cv2.contourArea(quad) < 0.15 * ANALYSIS[0] * ANALYSIS[1]:
            return {"ok": False, "error": "the corners do not look like the base: tap them in order"}
        calib.save(self.dir / "calibration.json")
        self._setup(calib)
        (self.dir / "reference.png").unlink(missing_ok=True)
        return {"ok": True, "message": "Angoli salvati. Ora togli tutto e premi Casa vuota.",
                "message_en": "Corners saved. Now clear the house and press Empty house."}

    def take_empty(self, frames: list[np.ndarray] | None = None) -> dict[str, Any]:
        if not self.calibrated:
            return {"ok": False, "error": "calibrate the corners first"}
        if frames is None:
            if self.grab is None:
                return {"ok": False, "error": "no camera"}
            frames = self.grab(EMPTY_FRAMES)
        frames = [self._fit(f) for f in frames if f is not None]
        if len(frames) < 3:
            return {"ok": False, "error": "no frames from the camera"}
        self.segmenter.set_reference(frames)
        cv2.imwrite(str(self.dir / "reference.png"), np.clip(self.segmenter.reference_bgr, 0, 255).astype(np.uint8))
        self._backgrounds()
        self._moved.update(shift=0.0, count=0)
        return {"ok": True, "message": "Casa vuota salvata.", "message_en": "Empty house saved."}

    def reset(self) -> dict[str, Any]:
        for name in ("calibration.json", "reference.png"):
            (self.dir / name).unlink(missing_ok=True)
        self.calib = self.segmenter = self.tracker = self.privacy = None
        self.tracks = []
        return {"ok": True}

    # ------------------------------------------------------------ frames
    @staticmethod
    def _fit(frame: np.ndarray) -> np.ndarray:
        if frame.shape[1::-1] != ANALYSIS:
            return cv2.resize(frame, ANALYSIS, interpolation=cv2.INTER_AREA)
        return frame

    def feed(self, frame: np.ndarray, now: float | None = None) -> list[Track]:
        now = time.time() if now is None else now
        t0 = time.perf_counter()
        small = self._fit(frame)
        if self.frame_at:
            dt = max(now - self.frame_at, 1e-3)
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt) if self.fps else 1.0 / dt
        self.frame, self.frame_at = small, now
        if not self.ready:
            self.tracks, self.observations = [], []
            return []
        obs, fg, _lab = self.segmenter.process(small, now)
        # most of the house different from the empty one: the hall light changed a lot, or the
        # camera was covered or knocked; people never cover that much
        share = float(np.count_nonzero(fg)) / max(float(np.count_nonzero(self.segmenter.mask)), 1.0)
        if share > 0.35:
            self._flooded_since = self._flooded_since or now
        else:
            self._flooded_since = 0.0
        self.observations = obs
        self.tracks = self.tracker.update(obs, now)
        # the hall light drifts slowly: follow it on the free floor, when nothing moves
        if now - self._last_ref_update > 5.0 and not any(o.hand for o in obs):
            self._last_ref_update = now
            self.segmenter.update_reference(small, fg, rate=0.02)
        if now - self._moved["checked"] > 30.0:
            self._check_moved(small, now)
        if self._record:
            self._record_frame(small, now)
        self.proc_ms = 0.9 * self.proc_ms + 0.1 * (time.perf_counter() - t0) * 1000.0
        return self.tracks

    def _check_moved(self, small: np.ndarray, now: float) -> None:
        """A bumped camera no longer sees the walls where the reference has them."""
        self._moved["checked"] = now
        ref = cv2.cvtColor(np.clip(self.segmenter.reference_bgr, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        cur = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        ref_e = cv2.Canny(ref, 40, 120).astype(np.float32)
        cur_e = cv2.Canny(cur, 40, 120).astype(np.float32)
        win = cv2.createHanningWindow(ref_e.shape[::-1], cv2.CV_32F)
        (dx, dy), response = cv2.phaseCorrelate(ref_e, cur_e, win)
        shift = float(np.hypot(dx, dy))
        self._moved["shift"] = round(shift, 1)
        self._moved["count"] = self._moved["count"] + 1 if shift > 3.0 and response > 0.05 else 0

    @property
    def moved(self) -> bool:
        return self._moved["count"] >= 2

    # ------------------------------------------------------------ queries
    def track_signature(self, track_id: str) -> tuple[list[float], str] | None:
        vt = self.tracker.track(track_id) if self.tracker else None
        if vt is None or len(vt.sig) != SIG_LEN:
            return None
        return [round(float(v), 5) for v in vt.sig], to_hex(vt.sig)

    def category_guess(self, track_id: str) -> str | None:
        vt = self.tracker.track(track_id) if self.tracker else None
        if vt is None or vt.obs is None:
            return None
        return vt.obs.category_guess

    def quality(self, track_id: str) -> list[dict[str, str]]:
        """What could make this one hard to recognize (shown when it is registered)."""
        vt = self.tracker.track(track_id) if self.tracker else None
        if vt is None:
            return []
        out = []
        names = {"floor": ("al pavimento", "the floor"), "lawn": ("ai prati", "the lawns"),
                 "wall": ("alle pareti", "the walls")}
        for key, sig in self._background.items():
            if distance(vt.sig, sig) < 0.22:
                it, en = names[key]
                out.append({"it": f"Il colore è molto simile {it}: potrei non vederlo bene.",
                            "en": f"Its colour is very close to {en}: I may not see it well."})
        age = max(time.time() - vt.since, 1e-3)
        if vt.hits < 0.5 * age * max(self.fps, 1.0) and age > 3:
            out.append({"it": "Compare e scompare: prova a spostarlo in un punto più libero.",
                        "en": "It keeps disappearing: try moving it to a clearer spot."})
        for ident in self.identities:
            if len(ident.signature) == SIG_LEN and distance(vt.sig, ident.signature) < ID_ACCEPT * 0.8:
                out.append({"it": f"Sembra uguale a {ident.name}: li distinguerò solo seguendoli.",
                            "en": f"It looks just like {ident.name}: I will tell them apart only by following them."})
                break
        return out

    def learned(self) -> dict[str, list[float]]:
        """Signatures of the identities seen with confidence, to update their gallery slowly."""
        out = {}
        if not self.tracker:
            return out
        for vt in self.tracker.tracks.values():
            if vt.identity and not vt.uncertain and vt.confidence > 0.6 and vt.obs is not None and not vt.carried:
                out[vt.identity] = [round(float(v), 5) for v in vt.sig]
        return out

    def status(self) -> dict[str, Any]:
        return {
            "calibrated": self.calibrated,
            "reference": bool(self.ready),
            "fps": round(self.fps, 1),
            "proc_ms": round(self.proc_ms, 1),
            "tracks": len(self.tracks),
            "hands": len(self.tracker.hands) if self.tracker else 0,
            "moved": self.moved,
            "flooded": bool(self._flooded_since and self.frame_at - self._flooded_since > 5.0),
            "shift_px": self._moved["shift"],
            "gains": self.segmenter.gains if self.segmenter else {},
            "recording": bool(self._record),
            "dataset": len(list(self.dataset_dir.glob("*.jpg"))),
        }

    # ------------------------------------------------------------ images that leave the board
    def image(self, overlay: bool = False, calibration: bool = False, width: int = 640) -> np.ndarray | None:
        if self.frame is None:
            return None
        img = (self.privacy or self._nominal_privacy).apply(self.frame)
        if calibration and self.calib:
            self._draw_layout(img)
        if overlay and self.calib:
            self._draw_tracks(img)
        if img.shape[1] != width:
            img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
        return img

    def jpeg(self, overlay: bool = False, calibration: bool = False, quality: int = 72) -> bytes | None:
        img = self.image(overlay, calibration)
        if img is None:
            return None
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def _draw_layout(self, img: np.ndarray) -> None:
        cal = self.calib
        lay = self.layout
        b = lay.base
        cv2.polylines(img, [np.round(cal.rect_polygon([b.x0, b.x1, b.y0, b.y1])).astype(np.int32)], True,
                      (0, 200, 255), 2, cv2.LINE_AA)
        for room in lay.rooms.values():
            r = room.rect
            color = (200, 120, 255) if room.private else (255, 255, 255)
            cv2.polylines(img, [np.round(cal.rect_polygon([r.x0, r.x1, r.y0, r.y1])).astype(np.int32)], True,
                          color, 1, cv2.LINE_AA)
        for d in lay.doors:
            r = d.rect
            cv2.polylines(img, [np.round(cal.rect_polygon([r.x0, r.x1, r.y0, r.y1])).astype(np.int32)], True,
                          (80, 220, 80), 1, cv2.LINE_AA)
        if self.segmenter is not None:
            excl = self.segmenter.mask == 0
            img[excl] = (img[excl] * 0.55).astype(np.uint8)
        # the walls at their real height: they must sit on the walls of the image
        for w in lay.raw.get("walls", []):
            poly = cal.rect_polygon(w["rect"], float(w.get("height", 0)))
            cv2.polylines(img, [np.round(poly).astype(np.int32)], True, (0, 255, 255), 1, cv2.LINE_AA)

    def _draw_tracks(self, img: np.ndarray) -> None:
        cal = self.calib
        names = {i.id: i.name for i in self.identities}
        for t in self.tracks:
            if t.carried:
                continue
            h = 95.0 if t.category == "person" else 45.0
            x, y = cal.image_of(np.array([[t.x, t.y]]), h)[0]
            label = names.get(t.identity or "") or CATEGORY_NAMES.get(t.category, {}).get("it", t.category)
            if t.uncertain:
                label += " ?"
            room = self.layout.room_label(t.room or "", "it") if t.room else ""
            text = f"{label} - {room}" if room else label
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            x0, y0 = int(x - tw / 2), int(y - 14)
            cv2.rectangle(img, (x0 - 3, y0 - th - 3), (x0 + tw + 3, y0 + 4), (30, 30, 30), -1)
            cv2.putText(img, text, (x0, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    # ------------------------------------------------------------ dataset (staff)
    def capture(self, count: int = 1) -> dict[str, Any]:
        frames = [self.frame] if count <= 1 or self.grab is None else self.grab(count)
        saved = 0
        for f in frames:
            if f is None:
                continue
            f = self._fit(f)
            if f is not self.frame:
                self.feed(f)
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
            img = (self.privacy or self._nominal_privacy).apply(f)
            cv2.imwrite(str(self.dataset_dir / f"{stamp}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            labels = self._labels()
            (self.dataset_dir / f"{stamp}.json").write_text(json.dumps(labels))
            saved += 1
        return {"ok": saved > 0, "message": f"{saved} immagini salvate", "message_en": f"{saved} images saved",
                "count": saved}

    def _labels(self) -> list[dict[str, Any]]:
        """Automatic labels: the boxes of the blobs, with the category of their track."""
        out = []
        names = {i.id: i.name for i in self.identities}
        for o in self.observations:
            if o.hand:
                continue
            best, best_d = None, 60.0
            for t in self.tracks:
                d = float(np.hypot(t.x - o.centroid_mm[0], t.y - o.centroid_mm[1]))
                if d < best_d:
                    best, best_d = t, d
            cat = best.category if best else o.category_guess
            out.append({"bbox": list(o.bbox), "category": cat,
                        "name": names.get(best.identity or "") if best else None})
        return out

    def export(self) -> dict[str, Any]:
        """The captures as a zip, with COCO and YOLO annotations."""
        images = sorted(self.dataset_dir.glob("*.jpg"))
        if not images:
            return {"ok": False, "error": "nothing captured yet"}
        out = self.dataset_dir.parent / "domotiq-dataset.zip"
        coco = {"images": [], "annotations": [], "categories": [{"id": i + 1, "name": c}
                                                                 for i, c in enumerate(COCO_CLASSES)]}
        ann_id = 1
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("yolo/classes.txt", "\n".join(COCO_CLASSES) + "\n")
            for n, path in enumerate(images, 1):
                img = cv2.imread(str(path))
                if img is None:
                    continue
                h, w = img.shape[:2]
                z.write(path, f"images/{path.name}")
                coco["images"].append({"id": n, "file_name": path.name, "width": w, "height": h})
                try:
                    labels = json.loads(path.with_suffix(".json").read_text())
                except (OSError, ValueError):
                    labels = []
                lines = []
                for lab in labels:
                    x, y, bw, bh = lab["bbox"]
                    cat = lab["category"] if lab["category"] in COCO_CLASSES else "object"
                    cid = COCO_CLASSES.index(cat)
                    coco["annotations"].append({"id": ann_id, "image_id": n, "category_id": cid + 1,
                                                "bbox": [x, y, bw, bh], "area": bw * bh, "iscrowd": 0,
                                                "attributes": {"name": lab.get("name")}})
                    ann_id += 1
                    lines.append(f"{cid} {(x + bw / 2) / w:.6f} {(y + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}")
                z.writestr(f"yolo/labels/{path.stem}.txt", "\n".join(lines) + ("\n" if lines else ""))
            z.writestr("coco/annotations.json", json.dumps(coco, indent=1))
        return {"ok": True, "path": str(out)}

    def clear_dataset(self) -> dict[str, Any]:
        shutil.rmtree(self.dataset_dir, ignore_errors=True)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        return {"ok": True}

    # ------------------------------------------------------------ recordings (staff)
    def start_recording(self, seconds: float = 60.0) -> dict[str, Any]:
        name = time.strftime("rec-%Y%m%d-%H%M%S")
        d = self.recordings_dir / name
        d.mkdir(parents=True, exist_ok=True)
        self._record = {"dir": d, "until": time.time() + max(5.0, min(seconds, 600.0)), "n": 0,
                        "log": open(d / "detections.jsonl", "w")}
        if self.calib:
            self.calib.save(d / "calibration.json")
        if self.segmenter and self.segmenter.reference_bgr is not None:
            ref = np.clip(self.segmenter.reference_bgr, 0, 255).astype(np.uint8)
            cv2.imwrite(str(d / "reference.jpg"), (self.privacy or self._nominal_privacy).apply(ref),
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
        return {"ok": True, "message": f"Registro {int(seconds)} s in {name}",
                "message_en": f"Recording {int(seconds)} s into {name}", "name": name}

    def _record_frame(self, small: np.ndarray, now: float) -> None:
        rec = self._record
        if now > rec["until"]:
            rec["log"].close()
            self._record = None
            return
        rec["n"] += 1
        img = (self.privacy or self._nominal_privacy).apply(small)
        cv2.imwrite(str(rec["dir"] / f"{rec['n']:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        rec["log"].write(json.dumps({
            "t": round(now, 3), "frame": rec["n"],
            "observations": [{"centroid": [round(v, 1) for v in o.centroid_mm], "bbox": list(o.bbox),
                              "area": round(o.area_mm2), "hand": o.hand, "guess": o.category_guess}
                             for o in self.observations],
            "tracks": [t.to_dict() for t in self.tracks],
        }) + "\n")
