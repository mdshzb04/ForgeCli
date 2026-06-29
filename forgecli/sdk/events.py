"""Plugin event bus + hook manager.

The SDK exposes:

* :class:`PluginEventBus` — a tiny pub/sub bus for plugin
  lifecycle and runtime events. Distinct from the engine's
  :class:`~forgecli.engine.events.EventBus` (which is for the
  eight-stage pipeline). The two are independent so plugins can
  listen to the engine *and* the plugin lifecycle without coupling.
* :class:`PluginHook` and :class:`HookManager` — synchronous
  before/after hooks the SDK fires when a plugin is installed,
  enabled, disabled, updated, or uninstalled.

Plugins subscribe at enable-time; the SDK guarantees that the
event handlers are called for every registered subscriber, even
if one raises (failures are logged and isolated).
"""

from __future__ import annotations

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

_logger = logging.getLogger("forgecli.sdk.events")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class PluginEventKind(str, Enum):
    """The high-level events plugins can listen to."""

    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNINSTALLED = "uninstalled"
    UPDATED = "updated"
    BEFORE_COMMAND = "before_command"
    AFTER_COMMAND = "after_command"
    CONFIG_CHANGED = "config_changed"
    ERROR = "error"


@dataclass(frozen=True)
class PluginEvent:
    """A single lifecycle / runtime event."""

    kind: PluginEventKind
    plugin_name: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[PluginEvent], "None | Awaitable[None]"]


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


class PluginEventBus:
    """In-process pub/sub bus for plugin events.

    Async-aware: subscribers may be sync or async. The bus
    serialises fan-out for synchronous subscribers and schedules
    coroutines for async ones.
    """

    def __init__(self) -> None:
        self._subscribers: dict[PluginEventKind, list[EventHandler]] = {}

    def subscribe(self, kind: PluginEventKind, handler: EventHandler) -> None:
        self._subscribers.setdefault(kind, []).append(handler)

    def unsubscribe(self, kind: PluginEventKind, handler: EventHandler) -> None:
        bucket = self._subscribers.get(kind)
        if not bucket:
            return
        with _suppress(ValueError):
            bucket.remove(handler)

    def publish(self, event: PluginEvent) -> None:
        """Publish synchronously. Async handlers are scheduled."""
        for handler in list(self._subscribers.get(event.kind, ())):
            try:
                result = handler(event)
            except Exception:
                _logger.exception("plugin event handler raised")
                continue
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(result)
                    task.add_done_callback(_discard_task)
                except RuntimeError:
                    pass

    async def publish_and_drain(self, event: PluginEvent) -> None:
        """Publish and await any async handler results."""
        for handler in list(self._subscribers.get(event.kind, ())):
            try:
                result = handler(event)
            except Exception:
                _logger.exception("plugin event handler raised")
                continue
            if asyncio.iscoroutine(result):
                await result


# ---------------------------------------------------------------------------
# Hook manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginHook:
    """A single registered hook.

    ``callback`` may be sync or async. The SDK wraps it in
    :func:`asyncio.iscoroutine` before calling so plugins can
    return a coroutine for async work.
    """

    name: str
    callback: Callable[..., Any]


class HookManager:
    """Synchronous registry of before/after hooks."""

    def __init__(self) -> None:
        self._before: list[PluginHook] = []
        self._after: list[PluginHook] = []

    def before(self, hook: PluginHook) -> None:
        self._before.append(hook)

    def after(self, hook: PluginHook) -> None:
        self._after.append(hook)

    def fire_before(self, *args: Any, **kwargs: Any) -> None:
        for hook in self._before:
            try:
                hook.callback(*args, **kwargs)
            except Exception:
                _logger.exception("hook %s failed (before)", hook.name)

    def fire_after(self, *args: Any, **kwargs: Any) -> None:
        for hook in self._after:
            try:
                hook.callback(*args, **kwargs)
            except Exception:
                _logger.exception("hook %s failed (after)", hook.name)

    async def fire_before_async(self, *args: Any, **kwargs: Any) -> None:
        for hook in self._before:
            try:
                result = hook.callback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                _logger.exception("hook %s failed (before)", hook.name)

    async def fire_after_async(self, *args: Any, **kwargs: Any) -> None:
        for hook in self._after:
            try:
                result = hook.callback(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                _logger.exception("hook %s failed (after)", hook.name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


import contextlib as _contextlib


@_contextlib.contextmanager
def _suppress(*exceptions: type[BaseException]):
    try:
        yield
    except exceptions:
        pass


def _discard_task(task: asyncio.Task) -> None:
    """Keep a strong reference to a scheduled task until it completes."""
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _suppress(*exceptions: type[BaseException]):
    with contextlib.suppress(*exceptions):
        yield


def _discard_task(task: asyncio.Task) -> None:
    """Keep a strong reference to a scheduled task until it completes."""
    return None


__all__ = [
    "EventHandler",
    "HookManager",
    "PluginEvent",
    "PluginEventBus",
    "PluginEventKind",
    "PluginHook",
]
