"""Core orchestration primitives: app context, DI container, events."""

from forgecli.core.container import Container
from forgecli.core.context import AppContext
from forgecli.core.errors import (
    ConfigError,
    ForgeCLIError,
    GitError,
    PipelineError,
    PluginError,
    ProviderError,
)
from forgecli.core.events import Event, EventBus
from forgecli.core.logging import configure_logging, get_logger
from forgecli.core.plugins import Plugin, discover_plugins, install_plugins
from forgecli.core.service import Service

__all__ = [
    "AppContext",
    "ConfigError",
    "Container",
    "Event",
    "EventBus",
    "ForgeCLIError",
    "GitError",
    "PipelineError",
    "Plugin",
    "PluginError",
    "ProviderError",
    "Service",
    "configure_logging",
    "discover_plugins",
    "get_logger",
    "install_plugins",
]
