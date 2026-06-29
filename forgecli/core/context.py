"""Application context: shared state object passed across the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forgecli.core.container import Container
from forgecli.core.events import EventBus
from forgecli.utils.paths import ProjectPaths

if TYPE_CHECKING:  # pragma: no cover - typing only
    from forgecli.config.loader import ConfigLoader
    from forgecli.config.settings import ForgeSettings


@dataclass
class AppContext:
    """Shared, mutable context for one CLI invocation.

    The context is created in :mod:`forgecli.cli.main` and explicitly
    passed to services that need it. It owns the configuration loader,
    the DI container, the event bus, and resolved filesystem paths.
    """

    paths: ProjectPaths
    loader: ConfigLoader
    settings: ForgeSettings | None = None
    container: Container = field(default_factory=Container)
    event_bus: EventBus = field(default_factory=EventBus)
    extras: dict[str, Any] = field(default_factory=dict)

    def resolve_settings(self, *, force: bool = False) -> ForgeSettings:
        """Load (or return cached) settings."""
        if self.settings is None or force:
            self.settings = self.loader.load(force=force)
        return self.settings

    def with_overrides(self, **values: Any) -> AppContext:
        """Return a shallow copy with extra values merged into ``extras``."""
        new = AppContext(
            paths=self.paths,
            loader=self.loader,
            settings=self.settings,
            container=self.container,
            event_bus=self.event_bus,
            extras={**self.extras, **values},
        )
        return new

    @property
    def cwd(self) -> Path:
        return self.paths.cwd
