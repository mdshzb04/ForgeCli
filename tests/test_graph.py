"""Tests for the code graph."""

from __future__ import annotations

from forgecli.graph.edge import Edge
from forgecli.graph.graph import CodeGraph
from forgecli.graph.node import EdgeKind, Node, NodeKind


def test_add_node_and_edge_round_trip() -> None:
    graph = CodeGraph()
    a = Node(id="file:a.py", kind=NodeKind.FILE, name="a.py")
    b = Node(id="file:b.py", kind=NodeKind.FILE, name="b.py")
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(Edge(source=a.id, target=b.id, kind=EdgeKind.IMPORTS))
    assert graph.has_node(a.id)
    assert graph.outgoing(a.id)[0].target == b.id
    assert graph.incoming(b.id)[0].source == a.id


def test_remove_node_drops_edges() -> None:
    graph = CodeGraph()
    a = Node(id="a", kind=NodeKind.MODULE, name="a")
    b = Node(id="b", kind=NodeKind.MODULE, name="b")
    graph.add_node(a)
    graph.add_node(b)
    graph.add_edge(Edge(source="a", target="b", kind=EdgeKind.IMPORTS))
    graph.remove_node("a")
    assert not graph.has_node("a")
    assert graph.incoming("b") == []


def test_stats_counts() -> None:
    graph = CodeGraph()
    graph.add_node(Node(id="a", kind=NodeKind.MODULE, name="a"))
    graph.add_node(Node(id="b", kind=NodeKind.MODULE, name="b"))
    graph.add_edge(Edge(source="a", target="b", kind=EdgeKind.CALLS))
    stats = graph.stats()
    assert stats["nodes"] == 2
    assert stats["edges"] == 1
