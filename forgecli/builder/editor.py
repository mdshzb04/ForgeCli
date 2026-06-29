"""File editing primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from forgecli.core.service import Service
from forgecli.utils.fs import atomic_write, read_text


@dataclass(frozen=True)
class FileEdit:
    """A single replacement operation targeting ``path``."""

    path: Path
    new_content: str


class Editor(Service):
    """Apply a batch of file edits atomically (best effort)."""

    name = "builder.editor"

    def apply(self, edits: Iterable[FileEdit]) -> list[Path]:
        """Write each edit to disk; return the list of touched paths."""
        touched: list[Path] = []
        for edit in edits:
            atomic_write(edit.path, edit.new_content)
            touched.append(Path(edit.path))
        return touched

    @staticmethod
    def read(path: Path) -> str:
        return read_text(path)
