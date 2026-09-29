# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The webcam: found by name, MJPEG, settings locked and re-applied.

The index of /dev/videoN changes from boot to boot, the name under
/dev/v4l/by-id does not. A reading thread keeps only the latest frame, so
the pipeline never works on an old one.

Automatic exposure and white balance would follow the figurines and the
coloured lights of the house and change the colours the recognition relies
on: after the calibration they are locked, together with the gain, the
anti-flicker at 50 Hz (the lights of an Italian fair hall) and the backlight
compensation off. The settings are re-applied every 60 s and after every
reconnection, since a camera that is unplugged forgets them.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import subprocess
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

MODES = [(1280, 960), (1280, 720), (640, 480)]


def find_device(preferred: str | None = None) -> str | None:
    if preferred and os.path.exists(preferred):
        return preferred
    ids = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    for p in ids:
        if "C270" in p or "046d" in p.lower():
            return p
    if ids:
        return ids[0]
    # a USB camera without a by-id entry: the first capture node that is not the board's own
    for p in sorted(glob.glob("/dev/video*")):
        try:
            name = open(f"/sys/class/video4linux/{os.path.basename(p)}/name").read().lower()
        except OSError:
            continue
        if any(k in name for k in ("webcam", "c270", "usb", "uvc")):
            return p
    return None


class Controls:
    """Camera controls through v4l2-ctl, with the names of old and new kernels."""

    ALIASES = {
        "auto_exposure": ["auto_exposure", "exposure_auto"],
        "exposure": ["exposure_time_absolute", "exposure_absolute"],
        "wb_auto": ["white_balance_automatic", "white_balance_temperature_auto"],
        "wb": ["white_balance_temperature"],
        "gain": ["gain"],
        "flicker": ["power_line_frequency"],
        "backlight": ["backlight_compensation"],
        "focus_auto": ["focus_automatic_continuous", "focus_auto"],
    }

    def __init__(self, device: str) -> None:
        self.device = device
        self.available: dict[str, dict[str, int]] = {}
        self.refresh()

    def refresh(self) -> None:
        self.available = {}
        try:
            out = subprocess.run(["v4l2-ctl", "-d", self.device, "--list-ctrls"], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return
        for line in out.splitlines():
            m = re.match(r"\s*(\w+)\s+0x[0-9a-f]+\s+\((\w+)\)\s*:(.*)", line)
            if not m:
                continue
            info = dict(re.findall(r"(\w+)=(-?\d+)", m.group(3)))
            self.available[m.group(1)] = {k: int(v) for k, v in info.items()}

    def name(self, key: str) -> str | None:
        return next((n for n in self.ALIASES.get(key, [key]) if n in self.available), None)

    def get(self, key: str) -> int | None:
        n = self.name(key)
        return self.available.get(n, {}).get("value") if n else None

    def set(self, values: dict[str, int]) -> bool:
        parts = []
        for key, value in values.items():
            n = self.name(key)
            if n is None or value is None:
                continue
            info = self.available[n]
            lo, hi = info.get("min"), info.get("max")
            if lo is not None and hi is not None:
                value = max(lo, min(hi, int(value)))
            parts.append(f"{n}={int(value)}")
        if not parts:
            return False
        try:
            # the automatic modes first: manual values are refused while they are on
            autos = [p for p in parts if p.startswith(("auto_exposure", "exposure_auto", "white_balance_a",
                                                       "white_balance_temperature_auto", "focus"))]
            rest = [p for p in parts if p not in autos]
            for group in (autos, rest):
                if group:
                    subprocess.run(["v4l2-ctl", "-d", self.device, "--set-ctrl", ",".join(group)],
                                   capture_output=True, timeout=5)
            self.refresh()
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    def automatic(self) -> None:
        self.set({"auto_exposure": 3, "wb_auto": 1, "flicker": 1, "backlight": 0})

    def lock(self, stored: dict | None = None) -> dict:
        """Freeze exposure, white balance and gain at the stored values, or at the current ones."""
        stored = stored or {}
        cur = {"exposure": self.get("exposure"), "wb": self.get("wb"), "gain": self.get("gain")}
        values = {k: stored.get(k) if stored.get(k) is not None else v for k, v in cur.items()}
        self.set({"auto_exposure": 1, "wb_auto": 0, "flicker": 1, "backlight": 0})
        self.set({k: v for k, v in values.items() if v is not None})
        return values


class Camera:
    def __init__(self, device: str | None = None, mode: tuple[int, int] | None = None, fps: int = 15) -> None:
        self.preferred = device
        self.mode_wanted = mode
        self.fps = fps
        self.device: str | None = None
        self.size: tuple[int, int] | None = None
        self.controls: Controls | None = None
        self._cap: cv2.VideoCapture | None = None
        self._raw = False
        self._frame: np.ndarray | None = None
        self._seq = 0
        self._at = 0.0
        self._lock = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.errors = 0
        self.reconnects = 0
        self.on_connect = None            # called after every (re)connection, to re-apply settings

    # ------------------------------------------------------------ opening
    def _open(self) -> bool:
        dev = find_device(self.preferred)
        if not dev:
            return False
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if not cap.isOpened():
            return False
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        modes = [self.mode_wanted] if self.mode_wanted else MODES
        for w, h in modes:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            if int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == w and int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == h:
                break
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # take the MJPEG data as it comes and decode it at half size: the analysis and the live view
        # work at 640 pixels, and a JPEG decoded at half size costs half as much as a full one
        self._raw = bool(cap.set(cv2.CAP_PROP_CONVERT_RGB, 0))
        ok, frame = cap.read()
        frame = self._decode(frame) if ok else None
        if frame is None and self._raw:
            self._raw = False
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)
            ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            return False
        self._cap = cap
        self.device = dev
        self.size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self.controls = Controls(dev)
        log.info("camera %s at %dx%d", dev, *self.size)
        if self.on_connect:
            try:
                self.on_connect(self)
            except Exception:  # noqa: BLE001
                log.exception("camera settings")
        return True

    def _decode(self, frame: np.ndarray | None) -> np.ndarray | None:
        if frame is None:
            return None
        if frame.ndim == 3:
            return frame                        # already decoded by the driver
        return cv2.imdecode(frame.reshape(-1), cv2.IMREAD_REDUCED_COLOR_2)

    def start(self) -> bool:
        ok = self._open()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()
        return ok

    @property
    def connected(self) -> bool:
        return self._cap is not None and time.time() - self._at < 3.0

    # ------------------------------------------------------------ reading
    def _run(self) -> None:
        while not self._stop.is_set():
            if self._cap is None:
                if not self._open():
                    time.sleep(2.0)
                    continue
                self.reconnects += 1
            ok, frame = self._cap.read()
            if ok and self._raw:
                frame = self._decode(frame)
            if not ok or frame is None:
                self.errors += 1
                if self.errors % 10 == 0:
                    log.warning("camera read failed, reopening")
                    self._cap.release()
                    self._cap = None
                time.sleep(0.05)
                continue
            with self._lock:
                self._frame = frame
                self._seq += 1
                self._at = time.time()
                self._lock.notify_all()

    def latest(self, after: int = -1, timeout: float = 1.0) -> tuple[int, np.ndarray | None]:
        """The newest frame, waiting for one newer than `after`."""
        with self._lock:
            if self._seq <= after:
                self._lock.wait(timeout)
            return self._seq, self._frame

    def flush(self, frames: int = 3, timeout: float = 2.0) -> None:
        """Wait for a few new frames, after a change of settings."""
        seq, _ = self.latest()
        end = time.time() + timeout
        while time.time() < end:
            s, _ = self.latest(seq, 0.5)
            if s >= seq + frames:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
