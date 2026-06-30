"""Common types for the review analyzer layer.

Every concrete analyzer subclasses :class:`Analyzer` and implements
:meth:`run`. The framework hands each analyzer a shared
:class:`AnalysisContext` (a pre-loaded view of the project) and the
analyzer returns a list of :class:`Finding` objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from typing import ClassVar

from forgecli.review.finding import Finding

# Directories we never want to recurse into.
_DEFAULT_IGNORES: tuple[str, ...] = (
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".eggs",
    "node_modules",
    "target",
    ".idea",
    ".vscode",
    "tests",
)


# File extensions we analyze.
_DEFAULT_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".pyi",
)


@dataclass
class SourceFile:
    """One source file under review."""

    path: Path
    text: str
    lines: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> SourceFile:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        return cls(path=path, text=text, lines=tuple(text.splitlines()))

    def line_at(self, line_number: int) -> str:
        if 1 <= line_number <= len(self.lines):
            return self.lines[line_number - 1]
        return ""


@dataclass
class AnalysisContext:
    """The shared state passed to every analyzer."""

    root: Path
    files: list[SourceFile] = field(default_factory=list)
    extras: dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        root: Path,
        *,
        extensions: Iterable[str] = _DEFAULT_EXTENSIONS,
        ignore: Iterable[str] = _DEFAULT_IGNORES,
    ) -> AnalysisContext:
        """Walk ``root`` and load every matching file."""
        root = Path(root).resolve()
        ignore_set = set(ignore)
        files: list[SourceFile] = []
        if root.is_file():
            files.append(SourceFile.load(root))
            return cls(root=root, files=files)
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in extensions:
                continue
            if any(part in ignore_set for part in path.parts):
                continue
            files.append(SourceFile.load(path))
        return cls(root=root, files=files)

    def get(self, path: Path) -> SourceFile | None:
        for file in self.files:
            if file.path == path:
                return file
        return None


class Analyzer(ABC):
    """Base class for review analyzers."""

    name: ClassVar[str] = "abstract"
    category: ClassVar[str] = "abstract"

    @abstractmethod
    def run(self, context: AnalysisContext) -> list[Finding]:
        """Return the findings produced by this analyzer."""


__all__ = [
    "AnalysisContext",
    "Analyzer",
    "SourceFile",
]
