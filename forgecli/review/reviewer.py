"""Top-level reviewer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from forgecli.review.finding import Finding


class Reviewer(ABC):
    """Strategy interface for analyzing changes and producing findings."""

    name: str = "abstract"

    @abstractmethod
    async def review(self, diff: str, *, context: dict | None = None) -> list[Finding]:
        """Return a list of :class:`Finding` for ``diff``."""
