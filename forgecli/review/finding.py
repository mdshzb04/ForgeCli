"""Finding and Severity value types shared by all review analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Severity levels for review findings."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        """Numeric weight used for sorting and aggregation."""
        return {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }[self]

    @property
    def is_blocking(self) -> bool:
        """A blocking finding is one we should refuse to merge."""
        return self is Severity.CRITICAL


@dataclass(frozen=True)
class Finding:
    """A single review observation.

    The ``category`` is one of: ``"security"``, ``"performance"``,
    ``"architecture"``, ``"complexity"``, ``"dead-code"``,
    ``"duplicates"``, ``"suggestions"``.
    """

    rule_id: str
    category: str
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    suggestion: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of this finding."""
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "suggestion": self.suggestion,
            "extra": self.extra,
        }


__all__ = ["Finding", "Severity"]
