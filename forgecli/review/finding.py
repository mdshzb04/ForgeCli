"""Code review primitives: findings and severity."""

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


@dataclass(frozen=True)
class Finding:
    """A single observation produced by a review pass."""

    rule_id: str
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    suggestion: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
