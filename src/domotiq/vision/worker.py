# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Vision in its own process.

The webcam, the pipeline and the tracker run in a child process, so a slow
frame never delays the web app or the voice and a crash in the camera
driver does not take the house down: the child is started again.

Parent and child talk over a pipe:

    parent -> child   ("identities", [...]) ("assign", track, identity) ("forget", identity)
                      ("dismiss", track) ("together", track, [identities])
                      ("lights", [rooms]) ("want", overlay) ("cmd", id, name, params) ("stop",)
    child -> parent   ("tracks", [...], status) ("jpeg", overlay, bytes) ("reply", id, result)
                      ("question", track, candidates) ("learn", {identity: signature}) ("log", text)
"""

from __future__ import annotations

import json
import logging
import multiprocessing as mp
import threading
import time
from pathlib import Path
from typing import Any

from ..model import Identity, Track
from .link import VisionLink

log = logging.getLogger(__name__)

TARGET_FPS = 10.0


# ==================================================================== child
def child_main(conn, cfg: dict[str, Any]) -> None:
    import signal
    # the house stops this process itself; Ctrl+C in a terminal reaches the whole group
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logging.basicConfig(level=cfg.get("log_level", logging.INFO),
                        format="%(levelname)s vision: %(message)s")
    import cv2  # noqa: F401  (imported here: the parent does not need it)

    from ..layout import Layout
    from .camera import Camera, Controls, average_stats, tune, valid_lock
    from .engine import Engine

    cv2.setNumThreads(2)
    layout = Layout.load(cfg["layout"])
    calib_dir = Path(cfg["calibration"])
    if cfg.get("device") == "synthetic":
        from .synthetic import SyntheticCamera
        camera = SyntheticCamera(layout)
    else:
        camera = Camera(cfg.get("device"), fps=15)
    lock_file = calib_dir / "camera.json"

    def apply_controls(cam: Camera) -> None:
        if cam.controls is None:
            return
        try:
            stored = json.loads(lock_file.read_text())
        except (OSError, ValueError):
            stored = None
        if valid_lock(stored):
            cam.controls.lock(stored)
            cam.set_balance(stored.get("balance"))
        else:
            cam.controls.automatic()
            cam.set_balance(None)

    camera.on_connect = apply_controls

    def grab(n: int) -> list:
        frames, seq = [], -1
        seq, _ = camera.latest()
        end = time.time() + n / 5.0 + 3.0
        while len(frames) < n and time.time() < end:
            s, f = camera.latest(seq, 0.5)
            if s > seq and f is not None:
                seq = s
                frames.append(f.copy())
        return frames

    engine = Engine(layout, calib_dir, Path(cfg["dataset"]), Path(cfg["recordings"]), grab)
    engine.set_privacy(cfg.get("blur_private", True))
    if cfg.get("device") != "synthetic":
        # nothing is recognized until the light of the webcam is set on the empty house
        try:
            engine.light_ok = valid_lock(json.loads(lock_file.read_text()))
        except (OSError, ValueError):
            engine.light_ok = False

    def ask(track: Track, candidates: list[str]) -> None:
        conn.send(("question", track.to_dict(), candidates))

    engine.on_question = ask

    def measure() -> tuple[float, tuple[float, float, float]]:
        camera.flush(frames=3)
        return average_stats(grab(2))

    def retune() -> None:
        """The light of the hall changed beyond what the correction of the rooms can follow: the webcam is set
        again on what it sees now. The calibration, the empty house and the presences stay as they are."""
        c: Controls | None = camera.controls
        if c is None:
            return
        logging.info("the light of the hall changed: setting the webcam again")
        camera.set_balance(None)
        try:
            values = tune(c, measure)
        except RuntimeError as e:
            logging.warning("setting the webcam again failed: %s", e)
            apply_controls(camera)                # back to the light it had
            engine.light_retuned(time.time())
            return
        camera.set_balance(values["balance"])
        lock_file.write_text(json.dumps(values))
        camera.flush()
        engine.light_retuned(time.time())

    def adjust() -> dict[str, Any]:
        """Let the camera find exposure and white balance on the empty house, then freeze them."""
        c: Controls | None = camera.controls
        if c is None:
            return {"ok": False, "error": "no camera"}
        camera.set_balance(None)
        try:
            values = tune(c, measure)
        except RuntimeError as e:
            c.automatic()
            return {"ok": False, "error": str(e)}
        camera.set_balance(values["balance"])
        lock_file.write_text(json.dumps(values))
        camera.flush()
        engine.light_ok = True
        result = engine.take_empty()
        result["camera"] = values
        return result

    commands = {
        "corners": lambda p: engine.set_corners(p.get("points") or []),
        # an empty house is saved with the light of the webcam set: the first time, both are done
        "empty": lambda p: (camera.flush(), engine.take_empty())[1] if engine.light_ok else adjust(),
        "adjust": lambda p: adjust(),
        "reset": lambda p: (lock_file.unlink(missing_ok=True), camera.controls and camera.controls.automatic(),
                            setattr(engine, "light_ok", cfg.get("device") == "synthetic"), engine.reset())[3],
        "capture": lambda p: engine.capture(int(p.get("count", 1))),
        "record": lambda p: engine.start_recording(float(p.get("seconds", 60))),
        "export": lambda p: engine.export(),
        "clear_dataset": lambda p: engine.clear_dataset(),
        "raw_frame": lambda p: {"ok": True, "jpeg": engine.jpeg(overlay=False, calibration=bool(p.get("overlay")))},
        "status": lambda p: {"ok": True, **engine.status()},
    }

    camera.start()
    want = {False: 0.0, True: 0.0}
    last_seq, last_status, last_learn, last_jpeg = -1, 0.0, time.time(), 0.0
    running = True
    while running:
        # ---- messages from the house
        while conn.poll():
            msg = conn.recv()
            kind = msg[0]
            if kind == "stop":
                running = False
                break
            try:
                if kind == "identities":
                    engine.set_identities([Identity.from_dict(d) for d in msg[1]])
                elif kind == "assign" and engine.tracker:
                    engine.tracker.assign(msg[1], msg[2])
                    # someone said who it is: its colours as seen now teach the house at once, and this look is
                    # one of its poses. Only if it looks like that character, though: an answer about the wrong
                    # blob (a light, another figurine) must not change what the character looks like
                    vt = engine.tracker.track(msg[1]) if msg[2] else None
                    ident = engine.tracker.identities.get(msg[2] or "")
                    fits = ident is not None and vt is not None and (
                        not len(ident.signature) or engine.tracker.fits_pose(ident, vt.sig))
                    if fits and vt.obs is not None and len(ident.signature):
                        engine.tracker.add_pose(ident, vt.sig, vt.obs.area_mm2, vt.obs.elongation)
                    sig = engine.track_signature(msg[1]) if fits else None
                    if sig:
                        conn.send(("taught", {msg[2]: sig[0]}, engine.learned_sizes(msg[2])))
                elif kind == "dismiss":
                    engine.dismiss(msg[1], time.time())
                elif kind == "together":
                    engine.together(msg[1], list(msg[2]), time.time())
                elif kind == "forget" and engine.tracker:
                    engine.tracker.forget(msg[1])
                elif kind == "lights":
                    engine.lights_changed(msg[1], time.time(), msg[2] if len(msg) > 2 else None)
                elif kind == "privacy":
                    engine.set_privacy(bool(msg[1]))
                elif kind == "want":
                    want[bool(msg[1])] = time.time()
                elif kind == "cmd":
                    _, rid, name, params = msg
                    fn = commands.get(name)
                    result = fn(params or {}) if fn else {"ok": False, "error": f"unknown command {name}"}
                    conn.send(("reply", rid, result))
                elif kind == "query":
                    _, rid, name, arg = msg
                    if name == "signature":
                        result = engine.track_signature(arg)
                    elif name == "category":
                        result = engine.category_guess(arg)
                    elif name == "quality":
                        result = engine.quality(arg)
                    else:
                        result = None
                    conn.send(("reply", rid, result))
            except Exception as e:  # noqa: BLE001
                logging.exception("vision message %s", kind)
                if kind in ("cmd", "query"):
                    conn.send(("reply", msg[1], {"ok": False, "error": str(e)}))
        if not running:
            break
        # ---- one frame
        start = time.time()
        seq, frame = camera.latest(last_seq, 0.5)
        now = time.time()
        if seq > last_seq and frame is not None:
            last_seq = seq
            try:
                tracks = engine.feed(frame, now)
            except Exception:  # noqa: BLE001
                logging.exception("frame failed")
                tracks = []
            conn.send(("tracks", [t.to_dict() for t in tracks], {"camera": camera.connected, "fps": engine.fps}))
            if camera.controls is not None and engine.retune_wanted(now):
                retune()
            if now - last_jpeg >= 0.2:                # the live view asks 5 pictures a second
                for overlay in (False, True):
                    if now - want[overlay] < 3.0:
                        jpg = engine.jpeg(overlay=overlay)
                        if jpg:
                            conn.send(("jpeg", overlay, jpg))
                            last_jpeg = now
        if now - last_status > 1.0:
            last_status = now
            st = engine.status()
            st.update(camera=camera.connected, device=camera.device,
                      size=list(camera.size) if camera.size else None, reconnects=camera.reconnects)
            conn.send(("status", st))
        poses = engine.learned_poses()
        if poses:
            conn.send(("poses", poses))
        if now - last_learn > 60.0:
            last_learn = now
            learned = engine.learned()
            if learned:
                conn.send(("learn", learned, engine.learned_sizes()))
        spare = 1.0 / TARGET_FPS - (time.time() - start)
        if spare > 0:
            time.sleep(spare)
    camera.stop()


# ==================================================================== parent
class VisionProcess(VisionLink):
    def __init__(self, paths, layout, settings, identities, device: str | None = None) -> None:
        self.paths = paths
        self.layout = layout
        self.settings = settings
        self.identities = identities
        self.cfg = {
            "layout": str(paths.data / "house.json"),
            "calibration": str(paths.calibration),
            "dataset": str(paths.dataset),
            "recordings": str(paths.recordings),
            "device": device or settings.get("camera.device"),
            "blur_private": settings.get("camera.blur_bathroom", True),
            "log_level": logging.getLogger().level or logging.INFO,
        }
        self._mp = mp.get_context("spawn")
        self._conn = None
        self._proc = None
        self._lock = threading.Lock()
        self._tracks: list[Track] = []
        self._tracks_at = 0.0
        self._jpeg: dict[bool, bytes | None] = {False: None, True: None}
        self._jpeg_at: dict[bool, float] = {False: 0.0, True: 0.0}
        self._status: dict[str, Any] = {}
        self._camera = False
        self._replies: dict[int, Any] = {}
        self._reply_cv = threading.Condition()
        self._rid = 0
        self._want_sent = {False: 0.0, True: 0.0}
        self._stopping = False
        self.on_question = None                     # callback(track, candidates), set by the app
        self.on_learn = None                        # callback({identity: signature})
        self._start()
        identities.bus.subscribe("identities_changed", lambda ev: self._send_identities())
        self._thread = threading.Thread(target=self._read, name="vision-link", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ process
    def _start(self) -> None:
        parent, child = self._mp.Pipe()
        proc = self._mp.Process(target=child_main, args=(child, self.cfg), name="domotiq-vision", daemon=True)
        proc.start()
        child.close()
        self._conn, self._proc = parent, proc
        self._send_identities()

    def _send(self, *msg) -> None:
        with self._lock:
            try:
                if self._conn is not None:
                    self._conn.send(msg)
            except (OSError, ValueError, BrokenPipeError):
                pass

    def _send_identities(self) -> None:
        self._send("identities", [i.to_dict() for i in self.identities.all()])

    def _read(self) -> None:
        while not self._stopping:
            conn = self._conn
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                if self._stopping:
                    return
                self._camera = False
                self._tracks = []
                time.sleep(2.0)
                if self._stopping:
                    return
                log.warning("vision process stopped, starting it again")
                try:
                    self._proc.join(timeout=1)
                except Exception:  # noqa: BLE001
                    pass
                self._start()
                continue
            kind = msg[0]
            if kind == "tracks":
                self._tracks = [Track(**d) for d in msg[1]]
                self._tracks_at = time.time()
                self._camera = bool(msg[2].get("camera"))
            elif kind == "jpeg":
                self._jpeg[bool(msg[1])] = msg[2]
                self._jpeg_at[bool(msg[1])] = time.time()
            elif kind == "status":
                self._status = msg[1]
                self._camera = bool(msg[1].get("camera"))
            elif kind == "reply":
                with self._reply_cv:
                    self._replies[msg[1]] = msg[2]
                    self._reply_cv.notify_all()
            elif kind == "question" and self.on_question:
                try:
                    self.on_question(Track(**msg[1]), msg[2])
                except Exception:  # noqa: BLE001
                    log.exception("vision question")
            elif kind == "learn":
                self._learn(msg[1], 0.1, msg[2] if len(msg) > 2 else None)
            elif kind == "taught":
                self._learn(msg[1], 0.5, msg[2] if len(msg) > 2 else None)
            elif kind == "poses":
                for ident_id, poses in msg[1].items():
                    try:
                        self.identities.update(ident_id, poses=poses)
                    except KeyError:
                        pass

    def _learn(self, learned: dict[str, list[float]], weight: float = 0.1,
               sizes: dict[str, float] | None = None) -> None:
        """The colour gallery and the size follow the identities slowly while they are recognized with
        confidence, and at once when someone says who a figurine is."""
        from .signature import blend
        sizes = sizes or {}
        for ident_id, sig in learned.items():
            ident = self.identities.get(ident_id)
            if ident is None:
                continue
            new = blend(ident.signature, sig, weight) if ident.signature else sig
            fields = {"signature": [round(float(v), 5) for v in new]}
            if sizes.get(ident_id):
                size = float(sizes[ident_id])
                fields["size"] = round(ident.size + weight * (size - ident.size), 1) if ident.size else size
            try:
                self.identities.update(ident_id, **fields)
            except KeyError:
                pass

    def _call(self, kind: str, name: str, arg: Any, timeout: float = 30.0) -> Any:
        with self._reply_cv:
            self._rid += 1
            rid = self._rid
        self._send(kind, rid, name, arg)
        end = time.time() + timeout
        with self._reply_cv:
            while rid not in self._replies:
                left = end - time.time()
                if left <= 0:
                    return None
                self._reply_cv.wait(left)
            return self._replies.pop(rid)

    # ------------------------------------------------------------ VisionLink
    @property
    def available(self) -> bool:  # type: ignore[override]
        return self._camera and self._proc is not None and self._proc.is_alive()

    def tracks(self) -> list[Track]:
        if time.time() - self._tracks_at > 2.0:
            return []
        return list(self._tracks)

    def jpeg(self, overlay: bool = False, since: float = 0.0) -> bytes | None:
        # the child encodes frames only while somebody asks for them: the cached one can be old
        now = time.time()
        if now - self._want_sent[overlay] > 1.0:
            self._want_sent[overlay] = now
            self._send("want", overlay)
        if since:
            return self._jpeg[overlay] if self._jpeg[overlay] is not None and self._jpeg_at[overlay] >= since else None
        return self._jpeg[overlay] or (self._jpeg[False] if overlay else None)

    def signature(self, track_id: str) -> tuple[list[float], str] | None:
        r = self._call("query", "signature", track_id, 5.0)
        return (r[0], r[1]) if r else None

    def category_guess(self, track_id: str) -> str | None:
        return self._call("query", "category", track_id, 5.0)

    def quality(self, track_id: str) -> list[dict[str, str]]:
        return self._call("query", "quality", track_id, 5.0) or []

    def assign(self, track_id: str, identity: str | None) -> None:
        self._send("assign", track_id, identity)

    def forget_identity(self, identity: str) -> None:
        self._send("forget", identity)

    def dismiss(self, track_id: str) -> None:
        self._send("dismiss", track_id)

    def together(self, track_id: str, identities: list[str]) -> None:
        self._send("together", track_id, list(identities))

    def lights_changed(self, rooms: list[str], animated: list[str] | None = None) -> None:
        self._send("lights", rooms, animated)

    def set_privacy(self, blur_private: bool) -> None:
        self.cfg["blur_private"] = bool(blur_private)
        self._send("privacy", bool(blur_private))

    def status(self) -> dict[str, Any]:
        return {"available": self.available, "alive": bool(self._proc and self._proc.is_alive()), **self._status}

    def command(self, name: str, **params: Any) -> dict[str, Any]:
        timeout = 60.0 if name in ("adjust", "empty", "capture", "export") else 15.0
        r = self._call("cmd", name, params, timeout)
        return r if isinstance(r, dict) else {"ok": False, "error": "the vision process did not answer"}

    def stop(self) -> None:
        self._stopping = True
        self._send("stop")
        if self._proc is not None:
            self._proc.join(timeout=3)
            if self._proc.is_alive():
                self._proc.terminate()
