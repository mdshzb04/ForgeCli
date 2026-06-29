"""Diff analysis utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiffStats:
    """Aggregated counters for a diff."""

    files: int
    additions: int
    deletions: int


class DiffAnalyzer:
    """Lightweight diff analyzer scaffold.

    Real implementations can wrap ``git diff`` or a structured diff
    library; the surface here stays small to keep the CLI in charge of
    presentation.
    """

    def analyze(self, diff: str) -> DiffStats:
        """Return basic stats for a unified diff ``diff`` string."""
        files = 0
        additions = 0
        deletions = 0
        for line in diff.splitlines():
            if line.startswith("diff --git"):
                files += 1
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        return DiffStats(files=files, additions=additions, deletions=deletions)
