"""Adapter that exposes a :class:`RepositoryGraph` backed by Graphify.

This module owns the translation from Graphify's on-disk ``graph.json``
into the typed :class:`GraphSnapshot` returned by
:class:`forgecli.graph.repository.RepositoryGraph`. It also routes the
high-level operations (``query``, ``explain``, ``shortest_path``,
``affected``) to the corresponding Graphify CLI subcommands.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forgecli.core.errors import ConfigError
from forgecli.graph.graphify import (
    GraphifyArtifacts,
    GraphifyClient,
    GraphifyNotFoundError,
)
from forgecli.graph.repository import (
    BuildResult,
    ExplainResult,
    GraphCommunity,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    QueryResult,
    RepositoryGraph,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable


_CITED_NODE_RE = re.compile(r"\b([A-Za-z0-9_./-]+(?:\.[A-Za-z0-9_./-]+)*)")


class GraphifyRepositoryGraph(RepositoryGraph):
    """A :class:`RepositoryGraph` powered by the Graphify CLI."""

    name = "graphify"

    def __init__(
        self,
        root: Path,
        *,
        client: GraphifyClient | None = None,
        artifacts: GraphifyArtifacts | None = None,
    ) -> None:
        self._root = Path(root).resolve()
        self._client = client or GraphifyClient()
        self._artifacts = artifacts or GraphifyArtifacts.for_root(self._root)
        self._cached: GraphSnapshot | None = None

    @property
    def root(self) -> Path:
        return self._root

    @property
    def client(self) -> GraphifyClient:
        return self._client

    @property
    def artifacts(self) -> GraphifyArtifacts:
        return self._artifacts

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        return await self._client.is_installed()

    async def install_hint(self) -> str:
        return (
            "Graphify is not installed.\n"
            "Install it with:  uv tool install graphifyy\n"
            "Docs:            https://graphifylabs.ai/"
        )

    # ------------------------------------------------------------------
    # Build / load
    # ------------------------------------------------------------------

    async def build(
        self,
        *,
        force: bool = False,
        no_cluster: bool = False,
        extra_args: Iterable[str] | None = None,
    ) -> BuildResult:
        outcome = await self._client.build(
            self._root,
            force=force,
            no_cluster=no_cluster,
            extra_args=tuple(extra_args or ()),
        )
        snapshot = self._snapshot_from_payload(outcome.graph_payload)
        self._cached = snapshot
        return BuildResult(
            snapshot=snapshot,
            artifacts={
                "graph_json": str(outcome.artifacts.graph_json),
                "manifest_json": str(outcome.artifacts.manifest_json),
            },
            raw_output=outcome.stdout,
        )

    async def load(self) -> GraphSnapshot:
        """Load a previously-built graph from ``self.artifacts.graph_json``."""
        if self._cached is not None:
            return self._cached
        if not self._artifacts.graph_json.exists():
            raise ConfigError(
                f"No graph.json found at {self._artifacts.graph_json}. "
                "Run `forge graph build` first."
            )
        payload = self._client.load_graph(self._artifacts.graph_json)
        snapshot = self._snapshot_from_payload(payload)
        self._cached = snapshot
        return snapshot

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    async def query(self, question: str, *, budget: int = 2000) -> QueryResult:
        snapshot = await self._ensure_loaded()
        answer = await self._client.query(
            self._root,
            question,
            budget=budget,
            graph_path=self._artifacts.graph_json,
        )
        cited = _extract_cited_nodes(answer, snapshot)
        return QueryResult(
            question=question,
            answer=answer.strip(),
            cited_nodes=tuple(cited),
        )

    async def explain(self, target: str) -> ExplainResult:
        snapshot = await self._ensure_loaded()
        text = await self._client.explain(
            self._root,
            target,
            graph_path=self._artifacts.graph_json,
        )
        related = _related_nodes(target, snapshot)
        return ExplainResult(
            target=target,
            explanation=text.strip(),
            related=tuple(related),
        )

    async def shortest_path(self, a: str, b: str) -> list[GraphEdge]:
        """Return the shortest edge path between ``a`` and ``b``.

        Implementation: the Graphify CLI emits a human-readable path; we
        reconstruct the edge list from the in-memory snapshot by BFS
        over node labels, then optionally cross-check against the CLI
        output for confirmation.
        """
        snapshot = await self._ensure_loaded()
        ids_a = _resolve_label(a, snapshot)
        ids_b = _resolve_label(b, snapshot)
        if not ids_a or not ids_b:
            return []
        edges = _bfs_shortest_path(snapshot, ids_a[0], ids_b[0])
        if not edges:
            # Fall back to invoking the Graphify CLI for confirmation.
            await self._client.path(
                self._root, a, b, graph_path=self._artifacts.graph_json
            )
        return edges

    async def affected(
        self,
        target: str,
        *,
        relation: Iterable[str] | None = None,
        depth: int = 2,
    ) -> list[GraphEdge]:
        snapshot = await self._ensure_loaded()
        ids = _resolve_label(target, snapshot)
        if not ids:
            return []
        # Always call Graphify for the authoritative traversal text.
        await self._client.affected(
            self._root,
            target,
            relation=relation,
            depth=depth,
            graph_path=self._artifacts.graph_json,
        )
        return _reverse_reachable(snapshot, ids[0], depth=depth, relation=relation)

    # ------------------------------------------------------------------
    # Snapshot construction
    # ------------------------------------------------------------------

    async def _ensure_loaded(self) -> GraphSnapshot:
        if self._cached is not None:
            return self._cached
        if self._artifacts.graph_json.exists():
            payload = self._client.load_graph(self._artifacts.graph_json)
            snapshot = self._snapshot_from_payload(payload)
            self._cached = snapshot
            return snapshot
        raise ConfigError(
            f"No graph.json found at {self._artifacts.graph_json}. "
            "Run `forge graph build` first."
        )

    def _snapshot_from_payload(self, payload: dict[str, Any]) -> GraphSnapshot:
        nodes: list[GraphNode] = []
        for raw in payload.get("nodes", []):
            nodes.append(
                GraphNode(
                    id=str(raw.get("id", raw.get("label", ""))),
                    label=str(raw.get("label", "")),
                    file_type=raw.get("file_type"),
                    source_file=raw.get("source_file"),
                    source_location=raw.get("source_location"),
                    community=raw.get("community"),
                    norm_label=raw.get("norm_label"),
                    extra={
                        k: v
                        for k, v in raw.items()
                        if k
                        not in {
                            "id",
                            "label",
                            "file_type",
                            "source_file",
                            "source_location",
                            "community",
                            "norm_label",
                        }
                    },
                )
            )

        edges: list[GraphEdge] = []
        for raw in payload.get("links", []):
            edges.append(
                GraphEdge(
                    source=str(raw.get("source", "")),
                    target=str(raw.get("target", "")),
                    relation=str(raw.get("relation", "")),
                    confidence=raw.get("confidence"),
                    confidence_score=raw.get("confidence_score"),
                    source_file=raw.get("source_file"),
                    source_location=raw.get("source_location"),
                    weight=float(raw.get("weight", 1.0) or 1.0),
                    extra={
                        k: v
                        for k, v in raw.items()
                        if k
                        not in {
                            "source",
                            "target",
                            "relation",
                            "confidence",
                            "confidence_score",
                            "source_file",
                            "source_location",
                            "weight",
                        }
                    },
                )
            )

        communities = _build_communities(nodes, edges, payload)

        return GraphSnapshot(
            root=str(self._root),
            nodes=tuple(nodes),
            edges=tuple(edges),
            communities=tuple(communities),
            directed=bool(payload.get("directed", False)),
            multigraph=bool(payload.get("multigraph", False)),
            metadata={"hyperedges": payload.get("hyperedges", [])},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_communities(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    payload: dict[str, Any],
) -> list[GraphCommunity]:
    """Group nodes by their ``community`` id; preserve numeric ordering."""
    if not nodes:
        return []
    counter: Counter[int] = Counter()
    members: dict[int, list[str]] = defaultdict(list)
    for node in nodes:
        if node.community is None:
            continue
        counter[node.community] += 1
        members[node.community].append(node.id)
    labels = payload.get("community_labels") or {}
    communities: list[GraphCommunity] = []
    for cid in sorted(counter):
        communities.append(
            GraphCommunity(
                id=cid,
                size=counter[cid],
                label=labels.get(str(cid)) or labels.get(cid),
                members=tuple(members[cid]),
            )
        )
    return communities


def _resolve_label(label_or_id: str, snapshot: GraphSnapshot) -> list[str]:
    """Return node ids matching ``label_or_id`` by id, label, or norm_label."""
    needle = label_or_id.strip()
    if not needle:
        return []
    ids: list[str] = []
    for node in snapshot.nodes:
        if needle == node.id or needle == node.label or needle == (node.norm_label or ""):
            ids.append(node.id)
    return ids


def _bfs_shortest_path(
    snapshot: GraphSnapshot, src: str, dst: str
) -> list[GraphEdge]:
    """Breadth-first shortest path over undirected edges."""
    if src == dst:
        return []
    adj: dict[str, list[tuple[str, GraphEdge]]] = defaultdict(list)
    for edge in snapshot.edges:
        adj[edge.source].append((edge.target, edge))
        adj[edge.target].append((edge.source, edge))
    visited = {src}
    queue: list[tuple[str, list[GraphEdge]]] = [(src, [])]
    while queue:
        node, path = queue.pop(0)
        for nxt, edge in adj.get(node, ()):
            if nxt in visited:
                continue
            new_path = [*path, edge]
            if nxt == dst:
                return new_path
            visited.add(nxt)
            queue.append((nxt, new_path))
    return []


def _reverse_reachable(
    snapshot: GraphSnapshot,
    start: str,
    *,
    depth: int,
    relation: Iterable[str] | None,
) -> list[GraphEdge]:
    """Return edges traversed when walking *into* ``start`` up to ``depth``."""
    rels = set(relation) if relation else None
    out: list[GraphEdge] = []
    seen: set[tuple[str, str, str]] = set()
    current = {start}
    for _ in range(max(depth, 0)):
        next_layer: set[str] = set()
        for edge in snapshot.edges:
            if edge.target in current and (rels is None or edge.relation in rels):
                key = (edge.source, edge.target, edge.relation)
                if key in seen:
                    continue
                seen.add(key)
                out.append(edge)
                next_layer.add(edge.source)
        current = next_layer
        if not current:
            break
    return out


def _related_nodes(target: str, snapshot: GraphSnapshot) -> list[GraphNode]:
    """Return nodes within one hop of any id matching ``target``."""
    ids = set(_resolve_label(target, snapshot))
    if not ids:
        return []
    related: list[GraphNode] = []
    seen: set[str] = set()
    for edge in snapshot.edges:
        if edge.source in ids and edge.target not in seen:
            node = snapshot.node(edge.target)
            if node is not None:
                related.append(node)
                seen.add(node.id)
        elif edge.target in ids and edge.source not in seen:
            node = snapshot.node(edge.source)
            if node is not None:
                related.append(node)
                seen.add(node.id)
    return related


def _extract_cited_nodes(answer: str, snapshot: GraphSnapshot) -> list[str]:
    """Pull node ids that look like ``name.py`` or symbol names from ``answer``."""
    cited: list[str] = []
    seen: set[str] = set()
    if not answer:
        return cited
    labels = {node.label for node in snapshot.nodes}
    ids = {node.id for node in snapshot.nodes}
    for token in _CITED_NODE_RE.findall(answer):
        if token in seen:
            continue
        if token in labels or token in ids:
            cited.append(token)
            seen.add(token)
    return cited


__all__ = ["GraphifyNotFoundError", "GraphifyRepositoryGraph"]
