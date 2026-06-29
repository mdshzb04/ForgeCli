"""High-level planner interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from forgecli.planner.plan import Plan


class Planner(ABC):
    """Strategy interface for turning a goal into a :class:`Plan`."""

    name: str = "abstract"

    @abstractmethod
    async def make_plan(self, goal: str, *, context: dict | None = None) -> Plan:
        """Build a :class:`Plan` that aims to satisfy ``goal``."""
