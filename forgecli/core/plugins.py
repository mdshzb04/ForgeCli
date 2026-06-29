"""Plugin discovery and lifecycle.

The plugin system is intentionally tiny for the scaffold: plugins are
loaded by entry point group (``forgecli.plugins``) and must implement
:class:`Plugin`. A real implementation may also support directory
plugins (``plugins_dir``) but the interface is the same.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import metadata
from typing import Any

from forgecli.core.context import AppContext
from forgecli.core.errors import PluginError


class Plugin(ABC):
    """Base class for ForgeCLI plugins."""

    name: str = "plugin"

    @abstractmethod
    def configure(self, context: AppContext) -> None:
        """Register services, commands, providers, etc. on ``context``."""


def discover_plugins(group: str = "forgecli.plugins") -> list[Plugin]:
    """Discover installed plugins via the ``group`` entry point."""
    plugins: list[Plugin] = []
    try:
        entries = metadata.entry_points(group=group)
    except Exception as exc:
        raise PluginError(f"Plugin discovery failed: {exc}") from exc
    for ep in entries:
        try:
            plugin_cls = ep.load()
            plugin = plugin_cls()  # type: ignore[call-arg]
        except Exception as exc:
            raise PluginError(f"Failed to load plugin {ep.name!r}: {exc}") from exc
        if not isinstance(plugin, Plugin):
            raise PluginError(
                f"Plugin {ep.name!r} must subclass forgecli.plugins.Plugin"
            )
        plugins.append(plugin)
    return plugins


def install_plugins(context: AppContext, plugins: list[Plugin]) -> None:
    """Configure each plugin against ``context``."""
    for plugin in plugins:
        plugin.configure(context)


__all__ = ["Any", "Plugin", "discover_plugins", "install_plugins"]
