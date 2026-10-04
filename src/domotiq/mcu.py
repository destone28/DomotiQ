# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""Talking to the microcontroller through arduino-router.

The Qwiic connector of the UNO Q belongs to the STM32U585, so every Modulino
is driven by the sketch in firmware/domotiq_mcu. Linux reaches it through
arduino-router: MessagePack-RPC over a unix socket, requests
[0, id, method, params] answered by [1, id, error, result]. To receive the
notifications the sketch sends (buttons, sensors), a process registers the
names it wants with "$/register"; they then arrive as [2, name, params].

One persistent connection carries both, and is reopened whenever the
router restarts or the MCU resets.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

import msgpack

log = logging.getLogger(__name__)

SOCKET = "/run/arduino-router.sock"
PROTOCOL = 1
NOTIFICATIONS = ("btn", "thermo", "mods")

# The reset line of the STM32U585, as the board's own router service drives it when it stops.
RESET_CHIP = "/dev/gpiochip1"
RESET_LINE = 38

# Bit order of `modules()`, the same as in the sketch.
MODULES = ("hub", "relay", "pixels_garage", "pixels_bedroom", "pixels_kitchen",
           "pixels_living", "thermo_bathroom", "pixels_bathroom", "thermo_thermostat",
           "buttons")

Notify = Callable[[str, list[Any]], Awaitable[None] | None]


class McuError(RuntimeError):
    pass


class RouterClient:
    def __init__(self, path: str = SOCKET, names: tuple[str, ...] = NOTIFICATIONS,
                 on_notify: Notify | None = None) -> None:
        self.path = path
        self.names = names
        self.on_notify = on_notify
        self.connected = asyncio.Event()
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._msgid = 0
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._writer:
            self._writer.close()

    async def _run(self) -> None:
        delay = 1.0
        while True:
            try:
                reader, writer = await asyncio.open_unix_connection(self.path)
            except OSError as e:
                log.debug("router not reachable: %s", e)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 10.0)
                continue
            delay = 1.0
            self._writer = writer
            reader_task = asyncio.create_task(self._read(reader))
            try:
                for name in self.names:
                    await self._request("$/register", [name], timeout=3.0, require_connected=False)
                self.connected.set()
                log.info("connected to arduino-router")
                await reader_task
            except (McuError, asyncio.TimeoutError, OSError) as e:
                log.warning("router connection lost: %s", e)
            finally:
                self.connected.clear()
                reader_task.cancel()
                self._fail_pending("disconnected")
                writer.close()
                self._writer = None
            await asyncio.sleep(1.0)

    async def _read(self, reader: asyncio.StreamReader) -> None:
        unpacker = msgpack.Unpacker(raw=False)
        while True:
            data = await reader.read(4096)
            if not data:
                raise OSError("router closed the connection")
            unpacker.feed(data)
            for msg in unpacker:
                self._handle(msg)

    def _handle(self, msg: Any) -> None:
        if not isinstance(msg, list) or not msg:
            return
        kind = msg[0]
        if kind == 1 and len(msg) >= 4:
            fut = self._pending.pop(msg[1], None)
            if fut and not fut.done():
                if msg[2] is not None:
                    fut.set_exception(McuError(str(msg[2])))
                else:
                    fut.set_result(msg[3])
        elif kind == 2 and len(msg) >= 3:
            if self.on_notify:
                try:
                    result = self.on_notify(msg[1], list(msg[2] or []))
                    if asyncio.iscoroutine(result):
                        asyncio.ensure_future(result)
                except Exception:  # noqa: BLE001
                    log.exception("notification %s failed", msg[1])
        elif kind == 0 and len(msg) >= 4 and self._writer:
            # nobody should call Linux methods on this connection
            self._writer.write(msgpack.packb([1, msg[1], "method not available", None]))

    def _fail_pending(self, reason: str) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(McuError(reason))
        self._pending.clear()

    async def _request(self, method: str, params: list[Any], timeout: float = 2.0,
                       require_connected: bool = True) -> Any:
        if require_connected and not self.connected.is_set():
            raise McuError("router not connected")
        if self._writer is None:
            raise McuError("router not connected")
        async with self._lock:
            self._msgid = (self._msgid + 1) % 0x7FFFFFFF
            msgid = self._msgid
            fut = asyncio.get_running_loop().create_future()
            self._pending[msgid] = fut
            self._writer.write(msgpack.packb([0, msgid, method, params], use_bin_type=True))
            await self._writer.drain()
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(msgid, None)

    async def call(self, method: str, *params: Any, timeout: float = 2.0) -> Any:
        return await self._request(method, list(params), timeout)


class Mcu:
    """The methods of the sketch, and the state reported back to the house."""

    def __init__(self, client: RouterClient | None = None) -> None:
        self.client = client
        self.version: int | None = None
        self.modules: dict[str, bool] = {m: False for m in MODULES}
        self.ok = False
        self.last_ping = 0.0
        self.relay_state: bool | None = None
        self.i2c: dict[str, Any] | None = None     # state of the Qwiic bus, None with older firmware

    @property
    def available(self) -> bool:
        return self.ok

    async def _call(self, method: str, *params: Any) -> Any:
        if self.client is None:
            raise McuError("no MCU")
        return await self.client.call(method, *params)

    async def check(self) -> bool:
        try:
            self.version = None
            self.version = int(await self._call("version"))
            if self.version != PROTOCOL:
                log.warning("the MCU speaks protocol %s, expected %s: reload the firmware",
                            self.version, PROTOCOL)
                self.ok = False
                return False
            await self._call("ping")
            self.set_modules(int(await self._call("modules")))
            try:
                self.i2c = parse_bus(int(await self._call("bus")))
            except (McuError, ValueError, TypeError):
                self.i2c = None
            self.ok = True
            self.last_ping = time.time()
        except (McuError, asyncio.TimeoutError, ValueError, TypeError):
            self.ok = False
            self.version = None         # no answer at all (a wrong protocol keeps its number)
        return self.ok

    async def reset(self) -> bool:
        """Restart the microcontroller (the sketch starts again and registers with the router).

        The sketch starts at power-up without waiting for Linux, so that the
        barbecue relay is switched off at once after a blackout. When Linux
        reboots, the router resets the microcontroller as it stops, and the
        sketch then starts before the new router is listening: its methods
        are never registered. A second reset, with the router ready, fixes it.
        """
        async def gpio(value: int) -> bool:
            proc = await asyncio.create_subprocess_exec(
                "gpioset", "-c", RESET_CHIP, "-t0", f"{RESET_LINE}={value}",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            return await proc.wait() == 0
        try:
            ok = await gpio(0)
            await asyncio.sleep(0.2)
            return await gpio(1) and ok
        except OSError:
            return False

    def set_modules(self, mask: int) -> None:
        self.modules = {name: bool(mask & (1 << i)) for i, name in enumerate(MODULES)}

    async def light(self, index: int, effect: int, r: int, g: int, b: int,
                    brightness: int, speed: int, duration_ms: int = 0) -> Any:
        return await self._call("light", index, effect, r, g, b, brightness, speed, duration_ms)

    async def party(self, bpm: float, seed: int, duration_ms: int, delay_ms: int) -> Any:
        return await self._call("party", int(bpm * 10), seed & 0x7FFFFFFF, duration_ms, delay_ms)

    async def relay(self, on: bool) -> bool | None:
        state = await self._call("relay", 1 if on else 0)
        self.relay_state = bool(state) if state in (0, 1, True, False) else None
        return self.relay_state

    async def leds(self, mask: int, blink: int = 0) -> Any:
        return await self._call("leds", mask & 7, blink & 7)

    async def limits(self, max_brightness: int, budget_ma: int) -> Any:
        return await self._call("limits", int(max_brightness), int(budget_ma))

    async def scan(self, channel: int) -> list[int]:
        found: list[int] = []
        for block in range(4):
            mask = int(await self._call("scan", channel, block))
            if mask < 0:
                raise McuError("scan timed out")
            found += [block * 32 + i for i in range(32) if mask & (1 << i)]
        return found


def parse_bus(value: int) -> dict[str, Any]:
    """The `bus` answer of the sketch: line levels now, and whether the last
    transaction found a line held low (the sketch then refuses them until
    the bus is free again)."""
    return {"scl": bool(value & 1), "sda": bool(value & 2), "held_low": bool(value & 4),
            "unsticks": (value >> 8) & 0xFF, "refused": (value >> 16) & 0x7FFF}


class SimulatedMcu(Mcu):
    """Stands in for the microcontroller on a PC and in the tests."""

    def __init__(self) -> None:
        super().__init__(None)
        self.calls: list[tuple] = []
        self.ok = True
        self.version = PROTOCOL
        self.set_modules((1 << len(MODULES)) - 1)
        self.i2c = parse_bus(3)
        self.leds_state = (0, 0)

    async def check(self) -> bool:
        return True

    async def _call(self, method: str, *params: Any) -> Any:
        self.calls.append((method, params))
        if method == "relay":
            return params[0]
        if method == "scan":
            return 0
        if method == "leds":
            self.leds_state = params
        return True
