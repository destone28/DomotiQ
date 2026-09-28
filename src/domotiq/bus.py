# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""A small in-process event bus.

Components never call each other to report what happened: they publish an
event and whoever cares subscribes. Handlers may be plain functions or
coroutines; a failing handler is logged and never stops the others.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

Handler = Callable[["Event"], Any | Awaitable[Any]]


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class Bus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the event loop, so other threads can publish safely."""
        self._loop = loop

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Subscribe to one event type, or to every event with "*"."""
        self._handlers[event_type].append(handler)

    def publish(self, event_type: str, _ts: float | None = None, **data: Any) -> Event:
        event = Event(event_type, data, _ts if _ts is not None else time.time())
        self.emit(event)
        return event

    def emit(self, event: Event) -> None:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is None and self._loop is not None and self._loop.is_running():
            # published from a worker thread: hand it over to the event loop
            self._loop.call_soon_threadsafe(self._dispatch, event)
        else:
            self._dispatch(event)

    def _dispatch(self, event: Event) -> None:
        for handler in list(self._handlers.get(event.type, ())) + list(self._handlers.get("*", ())):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    task = asyncio.ensure_future(result)
                    task.add_done_callback(_log_task_error)
            except Exception:  # noqa: BLE001 - one bad handler must not stop the rest
                log.exception("handler failed for %s", event.type)


def _log_task_error(task: asyncio.Future) -> None:
    if not task.cancelled() and task.exception():
        log.error("async handler failed", exc_info=task.exception())
