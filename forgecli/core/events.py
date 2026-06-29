"""A tiny pub/sub event bus used for decoupled logging and lifecycle hooks."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

Subscriber = Callable[["Event"], "None | Awaitable[None]"]


@dataclass(frozen=True)
class Event:
    """An immutable event payload."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Asynchronous-first pub/sub bus.

    Synchronous subscribers are invoked inline; async subscribers are
    scheduled via :func:`asyncio.create_task`. The bus is intentionally
    simple: subscribers cannot block the publisher and ordering is
    best-effort.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._pending_tasks: set[asyncio.Task[Any]] = set()

    def subscribe(self, name: str, callback: Subscriber) -> None:
        """Register ``callback`` for events named ``name``."""
        self._subscribers.setdefault(name, []).append(callback)

    def unsubscribe(self, name: str, callback: Subscriber) -> None:
        bucket = self._subscribers.get(name)
        if not bucket:
            return
        with contextlib.suppress(ValueError):
            bucket.remove(callback)

    async def publish(self, name: str, **payload: Any) -> None:
        """Publish an event, dispatching to all registered subscribers."""
        event = Event(name=name, payload=dict(payload))
        for callback in list(self._subscribers.get(name, ())):
            result = callback(event)
            if asyncio.iscoroutine(result):
                await result

    def emit(self, name: str, **payload: Any) -> None:
        """Synchronous variant of :meth:`publish`; async subs are not awaited."""
        event = Event(name=name, payload=dict(payload))
        for callback in list(self._subscribers.get(name, ())):
            result = callback(event)
            if asyncio.iscoroutine(result):
                # Fire-and-forget; require an event loop to be running.
                with contextlib.suppress(RuntimeError):
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(result)
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
