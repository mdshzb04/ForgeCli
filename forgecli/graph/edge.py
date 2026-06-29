"""Edge value type for the code graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from forgecli.graph.node import EdgeKind


@dataclass(frozen=True)
class Edge:
    """A directed edge in the code graph."""

    source: str
    target: str
    kind: EdgeKind
    weight: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)
