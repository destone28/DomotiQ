# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""The MCU client against a fake arduino-router on a unix socket."""

from __future__ import annotations

import asyncio

import msgpack
import pytest

from domotiq.mcu import MODULES, PROTOCOL, Mcu, McuError, RouterClient


class FakeRouter:
    """Answers like the sketch behind arduino-router, and can push notifications."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.registered: list[str] = []
        self.calls: list[tuple] = []
        self.writers: list[asyncio.StreamWriter] = []
        self.server: asyncio.base_events.Server | None = None
        self.relay = 0

    async def start(self) -> None:
        self.server = await asyncio.start_unix_server(self._client, self.path)

    async def stop(self) -> None:
        for w in self.writers:
            w.close()
        self.server.close()
        await self.server.wait_closed()
        self.writers.clear()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.writers.append(writer)
        unpacker = msgpack.Unpacker(raw=False)
        while True:
            data = await reader.read(4096)
            if not data:
                return
            unpacker.feed(data)
            for msg in unpacker:
                _, msgid, method, params = msg
                self.calls.append((method, tuple(params)))
                error, result = None, None
                if method == "$/register":
                    self.registered.append(params[0])
                    result = True
                elif method == "version":
                    result = PROTOCOL
                elif method == "ping":
                    result = True
                elif method == "modules":
                    result = 0b111
                elif method == "relay":
                    self.relay = params[0]
                    result = self.relay
                elif method == "scan":
                    # a Hub at 0x70 in block 3 on every channel, Pixels at 0x36 on channel 0
                    channel, block = params
                    mask = 0
                    if block == 3:
                        mask |= 1 << (0x70 - 96)
                    if channel == 0 and block == 1:
                        mask |= 1 << (0x36 - 32)
                    result = mask
                elif method == "light":
                    result = len(params) == 8
                else:
                    error = f"method {method} not available"
                writer.write(msgpack.packb([1, msgid, error, result]))
                await writer.drain()

    async def notify(self, name: str, params: list) -> None:
        for w in self.writers:
            w.write(msgpack.packb([2, name, params]))
            await w.drain()


async def _wait(cond, timeout: float = 3.0) -> None:
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.02)


def test_calls_notifications_and_reconnection(tmp_path):
    async def scenario():
        path = str(tmp_path / "router.sock")
        router = FakeRouter(path)
        await router.start()
        got: list[tuple] = []
        client = RouterClient(path, on_notify=lambda n, p: got.append((n, p)))
        client.start()
        await asyncio.wait_for(client.connected.wait(), 5)
        assert router.registered == ["btn", "dist", "thermo", "mods"]

        mcu = Mcu(client)
        assert await mcu.check()
        assert mcu.version == PROTOCOL
        assert [m for m, on in mcu.modules.items() if on] == list(MODULES[:3])
        assert await mcu.relay(True) is True and router.relay == 1
        assert await mcu.light(2, 1, 255, 170, 90, 60, 50) is True
        assert await mcu.scan(0) == [0x36, 0x70]
        with pytest.raises(McuError):
            await client.call("nonsense")

        await router.notify("btn", [0, 1])
        await router.notify("thermo", [0, 2430, 5210])
        await _wait(lambda: len(got) == 2)
        assert got[0] == ("btn", [0, 1]) and got[1][0] == "thermo"

        # the router restarts: the client reconnects and registers again
        await router.stop()
        await _wait(lambda: not client.connected.is_set())
        assert not await mcu.check()
        router.registered.clear()
        await router.start()
        await asyncio.wait_for(client.connected.wait(), 8)
        assert router.registered == ["btn", "dist", "thermo", "mods"]
        assert await mcu.check()
        await client.stop()
        await router.stop()

    asyncio.run(scenario())
