"""Abstract interface for a repository knowledge graph.

This module is the boundary between ForgeCLI's graph-aware features and any
concrete back-end (Graphify today; custom AST-based backends tomorrow). The
interface is intentionally small: build, query, explain, path, affected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GraphNode:
    """A typed view of a single node from the knowledge graph."""

    id: str
    label: str
    file_type: str | None = None
    source_file: str | None = None
    source_location: str | None = None
    community: int | None = None
    norm_label: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    """A typed view of a directed/undirected edge."""

    source: str
    target: str
    relation: str
    confidence: str | None = None
    confidence_score: float | None = None
    source_file: str | None = None
    source_location: str | None = None
    weight: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphCommunity:
    """A Leiden-detected community of nodes."""

    id: int
    size: int
    label: str | None = None
    members: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphSnapshot:
    """An immutable view of a fully-built knowledge graph."""

    root: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    communities: tuple[GraphCommunity, ...] = ()
    directed: bool = False
    multigraph: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def node(self, node_id: str) -> GraphNode | None:
        """Return the node with ``node_id`` or ``None``."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def neighbors(self, node_id: str) -> list[GraphEdge]:
        """Return all edges incident to ``node_id`` (in or out)."""
        return [e for e in self.edges if e.source == node_id or e.target == node_id]

    def search(self, query: str, *, limit: int = 20) -> list[GraphNode]:
        """Return nodes whose ``label`` or ``norm_label`` contain ``query``."""
        needle = query.lower()
        hits: list[GraphNode] = []
        for node in self.nodes:
            if needle in (node.label or "").lower() or needle in (node.norm_label or "").lower():
                hits.append(node)
                if len(hits) >= limit:
                    break
        return hits


@dataclass(frozen=True)
class BuildResult:
    """The outcome of :meth:`RepositoryGraph.build`."""

    snapshot: GraphSnapshot
    artifacts: dict[str, str] = field(default_factory=dict)
    raw_output: str = ""


@dataclass(frozen=True)
class QueryResult:
    """A natural-language answer produced by :meth:`RepositoryGraph.query`."""

    question: str
    answer: str
    cited_nodes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExplainResult:
    """A plain-language explanation of a node and its neighbors."""

    target: str
    explanation: str
    related: tuple[GraphNode, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


class RepositoryGraph(ABC):
    """Strategy interface for any repository knowledge graph backend."""

    name: str = "abstract"

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if the back-end is installed and runnable."""

    @abstractmethod
    async def build(self, *, force: bool = False) -> BuildResult:
        """Build (or rebuild) the graph rooted at the configured path."""

    @abstractmethod
    async def load(self) -> GraphSnapshot:
        """Load a previously-built graph from disk without rebuilding."""

    @abstractmethod
    async def query(self, question: str, *, budget: int = 2000) -> QueryResult:
        """Ask a free-form question; the back-end traverses the graph."""

    @abstractmethod
    async def explain(self, target: str) -> ExplainResult:
        """Return a plain-language explanation of ``target`` and its neighbors."""

    @abstractmethod
    async def shortest_path(self, a: str, b: str) -> list[GraphEdge]:
        """Return the shortest edge path between two node labels/ids."""

    @abstractmethod
    async def affected(
        self, target: str, *, relation: Iterable[str] | None = None, depth: int = 2
    ) -> list[GraphEdge]:
        """Return the reverse-traversal edges from ``target``."""


__all__ = [
    "BuildResult",
    "ExplainResult",
    "GraphCommunity",
    "GraphEdge",
    "GraphNode",
    "GraphSnapshot",
    "QueryResult",
    "RepositoryGraph",
]
