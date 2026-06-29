"""In-memory representation of the repository code graph."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from forgecli.graph.edge import Edge
from forgecli.graph.node import Node, NodeKind


class CodeGraph:
    """Mutable, in-memory graph of repository symbols and their relations.

    The graph is intentionally simple: nodes and edges are stored in
    dictionaries keyed by id. A real implementation may serialize to disk
    or back this with a proper graph database; the surface area stays the
    same.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._outgoing: dict[str, list[Edge]] = defaultdict(list)
        self._incoming: dict[str, list[Edge]] = defaultdict(list)

    # --- node operations -------------------------------------------------

    def add_node(self, node: Node) -> None:
        self._nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        for edge in self._outgoing.pop(node_id, ()):
            self._incoming.get(edge.target, []).remove(edge)
        for edge in self._incoming.pop(node_id, ()):
            self._outgoing.get(edge.source, []).remove(edge)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def nodes(self, kind: NodeKind | None = None) -> Iterator[Node]:
        for node in self._nodes.values():
            if kind is None or node.kind is kind:
                yield node

    # --- edge operations -------------------------------------------------

    def add_edge(self, edge: Edge) -> None:
        self._outgoing[edge.source].append(edge)
        self._incoming[edge.target].append(edge)

    def remove_edge(self, source: str, target: str, kind: Any | None = None) -> None:
        self._outgoing[source] = [
            e
            for e in self._outgoing.get(source, ())
            if not (e.target == target and (kind is None or e.kind is kind))
        ]
        self._incoming[target] = [
            e
            for e in self._incoming.get(target, ())
            if not (e.source == source and (kind is None or e.kind is kind))
        ]

    def outgoing(self, node_id: str) -> list[Edge]:
        return list(self._outgoing.get(node_id, ()))

    def incoming(self, node_id: str) -> list[Edge]:
        return list(self._incoming.get(node_id, ()))

    # --- bulk helpers -----------------------------------------------------

    def clear(self) -> None:
        self._nodes.clear()
        self._outgoing.clear()
        self._incoming.clear()

    def stats(self) -> dict[str, int]:
        return {
            "nodes": len(self._nodes),
            "edges": sum(len(v) for v in self._outgoing.values()),
        }
