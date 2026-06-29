"""Top-level builder pipeline orchestrator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from forgecli.builder.editor import Editor, FileEdit
from forgecli.builder.formatter import Formatter
from forgecli.core.service import Service


@dataclass
class BuildResult:
    """The outcome of a build run."""

    success: bool
    touched: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Builder(Service):
    """Coordinates editing, formatting, and verification of a change set."""

    name = "builder"

    def __init__(
        self,
        *,
        editor: Editor | None = None,
        formatter: Formatter | None = None,
        max_iterations: int = 3,
    ) -> None:
        super().__init__()
        self._editor = editor or Editor()
        self._formatter = formatter or Formatter()
        self._max_iterations = max_iterations

    @property
    def editor(self) -> Editor:
        return self._editor

    @property
    def formatter(self) -> Formatter:
        return self._formatter

    def build(self, edits: Iterable[FileEdit]) -> BuildResult:
        """Apply ``edits`` and run post-processing; placeholder for now."""
        touched = self._editor.apply(edits)
        if touched:
            self._formatter.format(touched)
        return BuildResult(success=True, touched=touched)
