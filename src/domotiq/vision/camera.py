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
        # a long exposure may slow the frames down: the tracking wants them steady
        "dyn_fps": ["exposure_dynamic_framerate", "exposure_auto_priority"],
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

    def limits(self, key: str) -> tuple[int, int] | None:
        info = self.available.get(self.name(key) or "", {})
        return (info["min"], info["max"]) if "min" in info and "max" in info else None

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

    def manual(self) -> None:
        self.set({"auto_exposure": 1, "wb_auto": 0, "dyn_fps": 0, "flicker": 1, "backlight": 0})

    def lock(self, stored: dict) -> dict:
        """Freeze exposure, white balance and gain at the values found by tune()."""
        values = {k: stored.get(k) for k in ("exposure", "wb", "gain") if stored.get(k) is not None}
        self.manual()
        self.set(values)
        return values


# The C270 does not report what its automatic modes chose: while they are on, the exposure and the white
# balance it gives back are the last manual values (the white balance even 0), and locking those left the
# picture almost black. So the values are found on the pictures: the brightness and the colours the
# automatic modes reach are measured, then reproduced in manual mode. Under some lights (the warm, greenish
# ones of the lab) no colour temperature of the webcam gives neutral colours, while its automatic mode does:
# what the temperature cannot correct, a fixed gain on each colour channel does, in software.
EXPOSURES = (3, 5, 8, 10, 15, 20, 30, 39, 50, 78, 100, 156, 200, 312, 400, 625)   # 0.1 ms
GAINS = (0, 16, 32, 64, 96, 128, 192, 255)
WB_STEPS = 9             # colour temperatures tried, across the whole range of the webcam
DARKER = 0.75            # some room for the lights of the house: the floor under them must not saturate
LUMA_MIN, LUMA_MAX = 50.0, 130.0
BALANCE_MIN, BALANCE_MAX = 0.4, 2.5


def valid_lock(stored: dict | None) -> bool:
    """Only a lock measured on the pictures: an older one could hold the white balance at 0."""
    return bool(stored and stored.get("exposure") and stored.get("balance"))


def picture_stats(frame: np.ndarray) -> tuple[float, tuple[float, float, float]]:
    """Brightness (0-255) and the mean of each channel (blue, green, red) of a picture."""
    small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA).astype(np.float32)
    b, g, r = (float(small[:, :, i].mean()) for i in range(3))
    return 0.114 * b + 0.587 * g + 0.299 * r, (b, g, r)


def average_stats(frames: list[np.ndarray]) -> tuple[float, tuple[float, float, float]]:
    """picture_stats() of a few pictures, averaged."""
    stats = [picture_stats(f) for f in frames if f is not None]
    if not stats:
        raise RuntimeError("no frames from the camera")
    n = len(stats)
    return sum(x[0] for x in stats) / n, tuple(sum(x[1][i] for x in stats) / n for i in range(3))


def _cast(bgr: tuple[float, float, float]) -> tuple[float, float]:
    b, g, r = (c + 1.0 for c in bgr)
    return float(np.log(b / g)), float(np.log(r / g))


def tune(controls, measure, settle: float = 3.0) -> dict:
    """Let the automatic modes settle, then find the manual exposure, gain and white balance that give the
    same picture (a quarter darker), and the gains that make its colours match. `measure()` waits for
    fresh pictures and returns picture_stats()."""
    controls.automatic()
    time.sleep(settle)
    luma_auto, bgr_auto = measure()
    target = min(LUMA_MAX, max(LUMA_MIN, luma_auto * DARKER))
    lo_wb, hi_wb = controls.limits("wb") or (2800, 6500)
    controls.manual()
    controls.set({"gain": GAINS[0], "wb": (lo_wb + hi_wb) // 2})

    def luma_at(exposure: int) -> float:
        controls.set({"exposure": exposure})
        return measure()[0]

    # the longest exposure that is not brighter than the target (the pictures grow brighter along the list)
    lo, hi = 0, len(EXPOSURES) - 1
    seen: dict[int, float] = {}
    while lo < hi:
        mid = (lo + hi + 1) // 2
        seen[mid] = luma_at(EXPOSURES[mid])
        if seen[mid] <= target:
            lo = mid
        else:
            hi = mid - 1
    best = lo
    if best + 1 < len(EXPOSURES):
        below = seen[best] if best in seen else luma_at(EXPOSURES[best])
        above = seen[best + 1] if best + 1 in seen else luma_at(EXPOSURES[best + 1])
        if abs(above - target) < abs(below - target):
            best += 1
    exposure = EXPOSURES[best]
    luma = luma_at(exposure)
    gain = GAINS[0]
    # a dark hall even at the longest exposure: some gain, as little as needed
    if luma < target * 0.85:
        for g in GAINS[1:]:
            controls.set({"gain": g})
            gain, luma = g, measure()[0]
            if luma >= target * 0.9:
                break
    # the colour temperature that leaves the smallest correction to the worse of blue and red
    want = _cast(bgr_auto)
    wb, error, bgr = lo_wb, float("inf"), bgr_auto
    for k in range(WB_STEPS):
        temp = int(round((lo_wb + (hi_wb - lo_wb) * k / (WB_STEPS - 1)) / 10.0)) * 10
        controls.set({"wb": temp})
        stats = measure()[1]
        got = _cast(stats)
        e = max(abs(got[0] - want[0]), abs(got[1] - want[1]))
        if e < error:
            wb, error, bgr = temp, e, stats
    controls.set({"wb": wb})
    # and what is left, as gains on the three channels that keep the brightness found above
    gb = (bgr_auto[0] + 1.0) / (bgr_auto[1] + 1.0) * (bgr[1] + 1.0) / (bgr[0] + 1.0)
    gr = (bgr_auto[2] + 1.0) / (bgr_auto[1] + 1.0) * (bgr[1] + 1.0) / (bgr[2] + 1.0)
    before = 0.114 * bgr[0] + 0.587 * bgr[1] + 0.299 * bgr[2]
    after = 0.114 * gb * bgr[0] + 0.587 * bgr[1] + 0.299 * gr * bgr[2]
    k = before / after if after > 0 else 1.0
    balance = [round(min(BALANCE_MAX, max(BALANCE_MIN, x * k)), 3) for x in (gb, 1.0, gr)]
    values = {"exposure": exposure, "wb": wb, "gain": gain, "balance": balance}
    log.info("camera tuned: %s (brightness %.0f for %.0f, automatic %.0f)", values, luma, target, luma_auto)
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
        self._lut: np.ndarray | None = None   # the fixed colour gains found by tune(), if any

    def set_balance(self, gains: list[float] | None) -> None:
        """Multiply blue, green and red by fixed gains (None: the pictures as they come)."""
        if not gains or all(abs(g - 1.0) < 1e-3 for g in gains):
            self._lut = None
            return
        ramp = np.arange(256, dtype=np.float32)
        self._lut = np.dstack([np.clip(ramp * g, 0, 255) for g in gains]).astype(np.uint8).reshape(256, 1, 3)

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
            lut = self._lut
            if ok and frame is not None and lut is not None:
                frame = cv2.LUT(frame, lut)
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
