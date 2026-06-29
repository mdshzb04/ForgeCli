"""Composable service lifecycle base class."""

from __future__ import annotations

from forgecli.core.logging import get_logger


class Service:
    """Base class for application services with structured logging."""

    name: str = "service"

    def __init__(self) -> None:
        self.log = get_logger(f"forgecli.{self.name}")

    async def start(self) -> None:  # pragma: no cover - placeholder
        """Bring the service online. Override in subclasses."""
        self.log.debug("start() called (no-op)")

    async def stop(self) -> None:  # pragma: no cover - placeholder
        """Tear the service down. Override in subclasses."""
        self.log.debug("stop() called (no-op)")
