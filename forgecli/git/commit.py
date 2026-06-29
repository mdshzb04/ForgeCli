"""Value types for git operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CommitAuthor:
    """Identity used when creating commits."""

    name: str
    email: str


@dataclass(frozen=True)
class CommitInfo:
    """Summary of a single commit."""

    sha: str
    short_sha: str
    author: CommitAuthor
    message: str
    timestamp: datetime
    files: list[str]
    extra: dict[str, Any] | None = None
