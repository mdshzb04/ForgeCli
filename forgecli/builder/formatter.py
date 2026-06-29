"""Source code formatting dispatcher."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from forgecli.core.service import Service


class Formatter(Service):
    """Dispatch code formatting to a language-specific backend.

    The default implementation is a no-op placeholder; concrete
    formatters (ruff, black, prettier, gofmt) will be plugged in here
    without changing call sites.
    """

    name = "builder.formatter"

    def __init__(self, *, backend: str = "auto") -> None:
        super().__init__()
        self._backend = backend

    @property
    def backend(self) -> str:
        return self._backend

    def format(self, paths: Iterable[Path]) -> list[Path]:
        """Format ``paths``; placeholder returns the input untouched."""
        return [Path(p) for p in paths]
