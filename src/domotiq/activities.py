# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house does: speak, notify, party, grill, change scene or language.

The same actions serve the rules, the voice commands and the buttons of the
web app, so a party started by a rule, by a phone or by voice behaves the
same way and respects the same cool-down.
"""

from __future__ import annotations

import asyncio
import re
import logging
import random
import time
from typing import TYPE_CHECKING, Any

from .lights import FLASH, LightRequest, RULE
from .model import CATEGORY_NAMES
from .scenes import scene_name
from .voice.answers import room as room_phrase

if TYPE_CHECKING:
    from .app import Context

log = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"\{(name|room|room_in|count|temp|rh|time)\}")
VERBOSITY_RANK = {"silent": 0, "normal": 1, "chatty": 2}

LANG_WORDS = {"it": {"it": "Italiano", "en": "Italian"}, "en": {"it": "English", "en": "English"}}


class Actions:
    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        self._party_cooldown_until = 0.0
        self._grill_cooldown_until = 0.0
        self._grill_task: asyncio.Task | None = None
        self._party_task: asyncio.Task | None = None

    # ================================================================ helpers
    @property
    def lang(self) -> str:
        return self.ctx.settings.get("voice.language", "it")

    def fill(self, text: dict[str, str] | str, ctx: dict[str, Any] | None, lang: str) -> str:
        if isinstance(text, dict):
            template = text.get(lang) or text.get("it") or text.get("en") or ""
        else:
            template = text or ""
        ctx = ctx or {}
        name = ctx.get("name") or ""
        if not name and ctx.get("category"):
            name = {"it": "qualcuno", "en": "someone"}[lang] if ctx["category"] == "person" else \
                CATEGORY_NAMES.get(ctx["category"], {}).get(lang, "")
        values = {
            "name": name or {"it": "qualcuno", "en": "someone"}[lang],
            "room": self.ctx.layout.room_label(ctx.get("room") or "", lang) if ctx.get("room") else "",
            "room_in": room_phrase(self.ctx, ctx.get("room"), lang) if ctx.get("room") else "",
            "count": ctx.get("count", ""),
            "temp": f"{ctx['temp']:.1f}" if isinstance(ctx.get("temp"), (int, float)) else "",
            "rh": f"{ctx['rh']:.0f}" if isinstance(ctx.get("rh"), (int, float)) else "",
            "time": time.strftime("%H:%M"),
        }
        # Only the exact placeholders, never str.format: names typed by visitors end up in these
        # sentences, and "{name:>999999999}" would build a gigabyte string.
        return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)

    def speaks(self, level: str = "normal") -> bool:
        current = VERBOSITY_RANK.get(self.ctx.settings.get("voice.verbosity", "normal"), 1)
        return current >= VERBOSITY_RANK.get(level, 1) and current > 0

    # ================================================================ Executor
    async def say(self, text: dict[str, str] | str, ctx: dict[str, Any] | None = None,
                  level: str | None = None) -> None:
        ctx = ctx or {}
        level = level or ctx.get("_verbosity", "normal")
        lang = self.lang
        line = self.fill(text, ctx, lang)
        if not line:
            return
        if isinstance(text, str):
            # a sentence given as it is (typed by the staff, written by the storyteller) may be in the other
            # language: it is read by the voice of the language it is written in
            from .voice.stories import sentence_lang
            lang = sentence_lang(line, lang)
        spoken = self.speaks(level)
        self.ctx.bus.publish("say", text=line, lang=lang, spoken=spoken)
        if spoken and self.ctx.voice is not None:
            await self.ctx.voice.speak(line, lang)

    async def sound(self, name: str) -> None:
        if self.ctx.audio is not None:
            await self.ctx.audio.effect(name)

    async def notify(self, level: str, text: dict[str, str] | str,
                     ctx: dict[str, Any] | None = None) -> None:
        both = {lang: self.fill(text, ctx, lang) for lang in ("it", "en")}
        self.ctx.store.add_event("notify", {"text": both}, level)
        self.ctx.bus.publish("notify", level=level, text=both)

    async def relay(self, on: bool, duration_s: float | None = None) -> None:
        if on:
            await self.grill(duration_s=duration_s, quiet=True)
        else:
            await self.grill_stop()

    async def scene(self, scene: str, announce: bool = True) -> bool:
        if not self.ctx.house.set_scene(scene):
            return False
        await self.ctx.lights.refresh()
        if announce:
            await self.say({"it": f"Scenario {scene_name(scene, 'it')}.",
                            "en": f"{scene_name(scene, 'en')} scene."})
        return True

    # ================================================================ party
    async def party(self) -> bool:
        now = time.time()
        if self.ctx.house.party_on or now < self._party_cooldown_until:
            return False
        cfg = self.ctx.settings.get("party")
        self.ctx.house.party_on = True
        self._party_task = asyncio.create_task(self._party(cfg))
        return True

    async def _party(self, cfg: dict[str, Any]) -> None:
        duration = float(cfg.get("duration_s", 20))
        bpm = float(cfg.get("bpm", 124))
        seed = random.randrange(1, 1 << 30)
        try:
            self.ctx.bus.publish("party", state="started", duration=duration)
            await self.say({"it": "Si balla!", "en": "Let's dance!"})
            latency_ms = 150
            if self.ctx.audio is not None:
                latency_ms = self.ctx.audio.latency_ms
            try:
                await self.ctx.mcu.party(bpm, seed, int(duration * 1000), latency_ms)
            except Exception:  # noqa: BLE001 - no MCU: the music still plays
                log.info("party without lights: MCU not available")
            self.ctx.lights.party_until = time.time() + duration
            self.ctx.bus.publish("lights_changed", lights=self.ctx.lights.state())
            if self.ctx.audio is not None:
                await self.ctx.audio.party_music(seed, duration, bpm)
            else:
                await asyncio.sleep(duration)
        finally:
            self.ctx.house.party_on = False
            self.ctx.lights.party_until = 0.0
            self._party_cooldown_until = time.time() + float(cfg.get("cooldown_s", 30))
            self.ctx.bus.publish("party", state="ended")
            self.ctx.bus.publish("lights_changed", lights=self.ctx.lights.state())
            await self.ctx.lights.refresh(force=True)
            await self.say({"it": "Festa finita!", "en": "The party is over!"})

    # ================================================================ grill
    async def grill(self, duration_s: float | None = None, quiet: bool = False) -> bool:
        now = time.time()
        if self.ctx.house.grill_on or now < self._grill_cooldown_until:
            return False
        cfg = self.ctx.settings.get("grill")
        duration = min(float(duration_s or cfg.get("duration_s", 20)), float(cfg.get("max_on_s", 120)))
        self.ctx.house.grill_on = True
        self._grill_task = asyncio.create_task(self._grill(duration, cfg, quiet))
        return True

    async def _grill(self, duration: float, cfg: dict[str, Any], quiet: bool) -> None:
        ready = False
        try:
            self.ctx.bus.publish("grill", state="started", duration=duration)
            if not quiet:
                await self.say({"it": "Accendo il barbecue!", "en": "Lighting the barbecue!"})
            await self._relay(True)
            await asyncio.sleep(duration)
            ready = True
        except asyncio.CancelledError:
            pass
        finally:
            await self._relay(False)
            self.ctx.house.grill_on = False
            self._grill_cooldown_until = time.time() + float(cfg.get("cooldown_s", 30))
            self.ctx.bus.publish("grill", state="ready" if ready and not quiet else "stopped")

    async def grill_stop(self) -> None:
        if self._grill_task and not self._grill_task.done():
            self._grill_task.cancel()
        else:
            await self._relay(False)

    async def _relay(self, on: bool) -> None:
        try:
            await self.ctx.mcu.relay(on)
        except Exception:  # noqa: BLE001
            log.warning("relay command failed (MCU not available)")

    # ================================================================ language, voice
    async def set_language(self, lang: str, announce: bool = True) -> bool:
        if lang not in ("it", "en"):
            return False
        self.ctx.settings.set("voice.language", lang)
        color = "#20e040" if lang == "it" else "#ff2010"
        self.ctx.lights.set("all", "flash", LightRequest("solid", color, 80, priority=FLASH), duration_s=1.2)
        await self.ctx.lights.refresh()
        await self.update_leds()
        self.ctx.bus.publish("language", language=lang)
        if announce:
            await self.say(LANG_WORDS[lang][lang])
        return True

    async def toggle_language(self) -> None:
        await self.set_language("en" if self.lang == "it" else "it")

    async def set_verbosity(self, level: str) -> bool:
        if level not in VERBOSITY_RANK:
            return False
        self.ctx.settings.set("voice.verbosity", level)
        self.ctx.bus.publish("verbosity", verbosity=level)
        return True

    async def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        self.ctx.settings.set("voice.volume", volume)
        if self.ctx.audio is not None:
            self.ctx.audio.set_volume(volume)
        self.ctx.bus.publish("volume", volume=volume)

    async def update_leds(self, listening: bool = False, waiting: bool = False) -> None:
        """LED 0 talk (on while listening), 1 intercom (blinks while waiting), 2 language (on = English)."""
        on = (1 if listening else 0) | (4 if self.lang == "en" else 0)
        blink = 2 if waiting else 0
        if self.ctx.settings.get("buttons.reversed"):
            on = ((on & 1) << 2) | (on & 2) | ((on & 4) >> 2)
            blink = ((blink & 1) << 2) | (blink & 2) | ((blink & 4) >> 2)
        try:
            await self.ctx.mcu.leds(on, blink)
        except Exception:  # noqa: BLE001
            pass

    # ================================================================ lights on demand
    async def light(self, room: str, color: str = "#ffffff", effect: str = "solid",
                    brightness: int = 60, duration_s: float | None = 120) -> None:
        self.ctx.lights.set(room, "manual", LightRequest(effect, color, brightness, priority=RULE + 5),
                            duration_s=duration_s)
        await self.ctx.lights.refresh()

    async def lights_off(self, room: str = "all") -> None:
        self.ctx.lights.clear(room, "manual")
        self.ctx.lights.set(room, "manual", LightRequest("off", "#000000", 0, priority=RULE + 5),
                            duration_s=60)
        await self.ctx.lights.refresh()

    async def lights_auto(self, room: str = "all") -> None:
        self.ctx.lights.clear(room, "manual")
        await self.ctx.lights.refresh()
