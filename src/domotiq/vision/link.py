# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the rest of the house needs from vision, whatever produces the tracks.

`VisionLink` is the interface; `NoVision` stands in when there is no camera;
the real implementation (a worker process) lives in `domotiq.vision.worker`.
"""

from __future__ import annotations

from typing import Any

from ..model import Track


class VisionLink:
    available = False

    def tracks(self) -> list[Track]:
        return []

    def jpeg(self, overlay: bool = False, since: float = 0.0) -> bytes | None:
        """The latest frame for the live view, already privacy-filtered (names drawn on it if asked).

        With `since`, only a frame made after that moment, or None.
        """
        return None

    def unknown_tracks(self) -> list[Track]:
        return [t for t in self.tracks() if not t.identity and not t.carried]

    def signature(self, track_id: str) -> tuple[list[float], str] | None:
        return None

    def assign(self, track_id: str, identity: str | None, explicit: bool = False) -> None:
        pass

    def forget_identity(self, identity: str) -> None:
        pass

    def dismiss(self, track_id: str) -> None:
        """Nothing is there (a reflection, a hand): the vision forgets what it saw."""

    def together(self, track_id: str, identities: list[str]) -> None:
        """What the vision sees there is these characters, touching each other: all of them are there."""

    def category_guess(self, track_id: str) -> str | None:
        return None

    def quality(self, track_id: str) -> list[dict[str, str]]:
        """Warnings about how well this track can be recognized, as {"it": ..., "en": ...}."""
        return []

    def lights_changed(self, rooms: list[str], animated: list[str] | None = None, lit: list[str] | None = None) -> None:
        """The house changed the light of these rooms (the pipeline measures them again); `animated`: the
        rooms whose light is animated now, where figurines may seem to shake."""

    def pause(self, on: bool) -> None:
        """A party: what the webcam sees is not looked at until it ends (the presences stay as they are)."""

    def status(self) -> dict[str, Any]:
        return {"available": self.available}

    def set_privacy(self, blur_private: bool) -> None:
        """Whether the bathroom is blurred in the images that leave the board."""

    def set_figures(self, on: bool, consent: bool = False) -> None:
        """Whether the network that knows the figurines gives its second opinion, and whether nothing new is told
        to the house before it sees a figurine there."""

    def set_registering(self, on: bool) -> None:
        """A new character is being registered: its figurine is born whatever the network says."""

    def set_collect(self, on: bool, mb: int) -> None:
        """Whether what the webcam sees is kept to teach the network, and in how much space."""

    def command(self, name: str, **params: Any) -> dict[str, Any]:
        """Calibration, capture and the other operations of the calibration page."""
        return {"ok": False, "error": "no camera"}

    def stop(self) -> None:
        pass


class NoVision(VisionLink):
    pass
