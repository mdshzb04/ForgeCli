"""Repository indexer: walk the filesystem and populate the :class:`CodeGraph`."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from forgecli.core.service import Service
from forgecli.graph.graph import CodeGraph
from forgecli.graph.node import Node, NodeKind
from forgecli.utils.fs import iter_files


class Indexer(Service):
    """Walks a project directory and adds file-level nodes to the graph.

    The real implementation will plug in tree-sitter to extract symbols;
    this scaffold only produces file/package nodes and leaves symbol
    extraction to language-specific analyzers added later.
    """

    name = "graph.indexer"

    DEFAULT_GLOBS: tuple[str, ...] = ("**/*.py", "**/*.ts", "**/*.js", "**/*.go", "**/*.rs")

    def __init__(
        self,
        graph: CodeGraph,
        *,
        root: Path,
        languages: Iterable[str] | None = None,
        ignore_patterns: Iterable[str] | None = None,
    ) -> None:
        super().__init__()
        self._graph = graph
        self._root = Path(root).resolve()
        self._languages = list(languages) if languages else ["python", "typescript"]
        self._ignore = list(ignore_patterns) if ignore_patterns else []

    @property
    def root(self) -> Path:
        return self._root

    def index(self) -> dict[str, Any]:
        """Walk ``root`` and add file nodes to the graph.

        Returns a small summary useful for logging and tests.
        """
        files = list(self._discover_files())
        for path in files:
            rel = str(path.relative_to(self._root))
            node = Node(
                id=f"file:{rel}",
                kind=NodeKind.FILE,
                name=path.name,
                path=rel,
                language=self._infer_language(path),
            )
            self._graph.add_node(node)
        return {"files_indexed": len(files)}

    def _discover_files(self) -> Iterable[Path]:
        for path in iter_files(self._root, list(self.DEFAULT_GLOBS)):
            if not path.is_file():
                continue
            if any(part in self._ignore for part in path.parts):
                continue
            yield path

    @staticmethod
    def _infer_language(path: Path) -> str | None:
        suffix = path.suffix.lower()
        return {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
        }.get(suffix)
