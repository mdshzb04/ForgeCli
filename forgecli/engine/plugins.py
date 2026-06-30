"""Plugin hooks for the Execution Engine.

Plugins extend the engine by:

* registering new :class:`~forgecli.engine.execution.Stage`
  implementations;
* adding event subscribers (for telemetry, custom sinks, etc.);
* registering themselves with the global :class:`PluginRegistry`.

Two hook points are provided:

* ``before_pipeline(context)`` — runs before the first stage.
* ``after_pipeline(result)`` — runs after the last stage (or on
  failure / cancellation).

Plugins are also :class:`Stage` instances themselves, so a plugin
can drop in a single stage that replaces a default stage by name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from forgecli.engine.execution import EngineResult, Stage
from forgecli.plugins import PluginRegistry

if TYPE_CHECKING:  # pragma: no cover - typing only
    from forgecli.engine.context import EngineContext
    from forgecli.engine.events import EventBus


# A plugin is anything callable that takes a PluginRegistry.
EnginePluginFactory = Callable[[PluginRegistry], None]


@dataclass
class PluginHook:
    """A single async lifecycle hook fired by the engine.

    Hooks fire in the order they were registered. A hook that
    raises is logged on the event bus but does *not* abort the
    pipeline — plugins must not break the engine.
    """

    name: str
    callback: Callable[[], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_plugin(
    plugin_factory: EnginePluginFactory,
    *,
    registry: PluginRegistry,
) -> None:
    """Register a plugin with the given :class:`PluginRegistry`."""
    plugin_factory(registry)


# ---------------------------------------------------------------------------
# Hook manager (per-engine)
# ---------------------------------------------------------------------------


class HookManager:
    """Holds the before/after hooks for a single engine instance."""

    def __init__(self) -> None:
        self._before: list[PluginHook] = []
        self._after: list[PluginHook] = []

    def add_before(self, hook: PluginHook) -> None:
        self._before.append(hook)

    def add_after(self, hook: PluginHook) -> None:
        self._after.append(hook)

    async def fire_before(self, context: EngineContext, bus: EventBus) -> None:
        from forgecli.engine.events import LogLevel, TextLogEvent

        for hook in self._before:
            try:
                result = hook.callback()
                if result is not None:
                    await result
            except Exception as exc:
                bus.publish(
                    TextLogEvent(
                        level=LogLevel.WARN,
                        source=f"plugin:{hook.name}",
                        message=f"before-pipeline hook failed: {exc}",
                        run_id=context.run_id,
                    )
                )

    async def fire_after(
        self, result: EngineResult, bus: EventBus
    ) -> None:
        from forgecli.engine.events import LogLevel, TextLogEvent

        for hook in self._after:
            try:
                value = hook.callback()
                if value is not None:
                    await value
            except Exception as exc:
                bus.publish(
                    TextLogEvent(
                        level=LogLevel.WARN,
                        source=f"plugin:{hook.name}",
                        message=f"after-pipeline hook failed: {exc}",
                        run_id=result.context.run_id,
                    )
                )


# ---------------------------------------------------------------------------
# Stage-level plugin helper
# ---------------------------------------------------------------------------


def stage_as_plugin(stage: Stage) -> EnginePluginFactory:
    """Wrap a :class:`Stage` as a plugin factory that auto-registers
    itself in any :class:`PluginRegistry`.

    The plugin is registered under the stage's name; calling it
    again replaces the previous binding (last writer wins).
    """
    def _factory(registry: PluginRegistry) -> None:
        registry.register_stage(stage)  # type: ignore[attr-defined]

    return _factory


__all__ = [
    "EnginePluginFactory",
    "HookManager",
    "PluginHook",
    "register_plugin",
    "stage_as_plugin",
]
