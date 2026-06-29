"""Tests for the Graphify-backed :class:`RepositoryGraph` adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from forgecli.core.errors import ConfigError
from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
from forgecli.graph.graphify import GraphifyArtifacts, GraphifyClient
from forgecli.graph.repository import (
    ExplainResult,
    GraphSnapshot,
    QueryResult,
)


def _write_graph(tmp_path: Path, *, nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir(exist_ok=True)
    graph_json = out / "graph.json"
    graph_json.write_text(
        json.dumps(
            {
                "directed": False,
                "multigraph": False,
                "graph": {},
                "nodes": nodes,
                "links": links,
                "hyperedges": [],
            }
        ),
        encoding="utf-8",
    )
    (out / "manifest.json").write_text("{}", encoding="utf-8")
    return graph_json


def _client_with_files(tmp_path: Path) -> GraphifyClient:
    return GraphifyClient(executable="/usr/bin/graphify")


def test_load_snapshot_from_payload(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[
            {"id": "a", "label": "a.py", "file_type": "code", "community": 0},
            {"id": "a_foo", "label": "foo()", "file_type": "code", "community": 0},
            {"id": "b", "label": "b.py", "file_type": "code", "community": 1},
        ],
        links=[
            {"source": "a", "target": "a_foo", "relation": "contains", "confidence": "EXTRACTED"},
            {"source": "b", "target": "a_foo", "relation": "calls", "confidence": "INFERRED", "confidence_score": 0.7},
        ],
    )
    backend = GraphifyRepositoryGraph(root=tmp_path, client=_client_with_files(tmp_path))
    snap = asyncio.run(backend.load())
    assert isinstance(snap, GraphSnapshot)
    assert len(snap.nodes) == 3
    assert len(snap.edges) == 2
    assert len(snap.communities) == 2

    # search() works on labels
    matches = snap.search("foo")
    assert any(n.id == "a_foo" for n in matches)

    # node() and neighbors()
    node = snap.node("a")
    assert node is not None and node.label == "a.py"
    incident = snap.neighbors("a")
    assert any(e.target == "a_foo" for e in incident)


def test_load_raises_when_graph_missing(tmp_path: Path) -> None:
    backend = GraphifyRepositoryGraph(root=tmp_path, client=_client_with_files(tmp_path))
    with pytest.raises(ConfigError):
        asyncio.run(backend.load())


def test_query_extracts_cited_nodes(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[
            {"id": "a", "label": "a.py", "file_type": "code", "community": 0},
            {"id": "b", "label": "b.py", "file_type": "code", "community": 0},
        ],
        links=[],
    )
    client = _client_with_files(tmp_path)
    backend = GraphifyRepositoryGraph(root=tmp_path, client=client)

    async def fake_query(*args, **kwargs):
        return "auth lives in a.py and b.py (L1)"

    client.query = AsyncMock(side_effect=fake_query)  # type: ignore[method-assign]
    result: QueryResult = asyncio.run(backend.query("where is auth?"))
    assert result.question == "where is auth?"
    assert "a.py" in result.answer
    assert "a.py" in result.cited_nodes
    assert "b.py" in result.cited_nodes


def test_explain_returns_related_nodes(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[
            {"id": "a", "label": "a.py", "file_type": "code", "community": 0},
            {"id": "a_foo", "label": "foo()", "file_type": "code", "community": 0},
            {"id": "b", "label": "b.py", "file_type": "code", "community": 0},
        ],
        links=[
            {"source": "a", "target": "a_foo", "relation": "contains"},
            {"source": "b", "target": "a", "relation": "imports"},
        ],
    )
    client = _client_with_files(tmp_path)
    backend = GraphifyRepositoryGraph(root=tmp_path, client=client)

    async def fake_explain(*args, **kwargs):
        return "a.py is a Python module containing foo()."

    client.explain = AsyncMock(side_effect=fake_explain)  # type: ignore[method-assign]
    result: ExplainResult = asyncio.run(backend.explain("a.py"))
    assert result.target == "a.py"
    assert "foo()" in result.explanation
    related_labels = {n.label for n in result.related}
    assert "foo()" in related_labels
    assert "b.py" in related_labels


def test_shortest_path_finds_two_hop(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[
            {"id": "a", "label": "a.py"},
            {"id": "b", "label": "b.py"},
            {"id": "c", "label": "c.py"},
        ],
        links=[
            {"source": "a", "target": "b", "relation": "imports"},
            {"source": "b", "target": "c", "relation": "imports"},
        ],
    )
    backend = GraphifyRepositoryGraph(root=tmp_path, client=_client_with_files(tmp_path))
    edges = asyncio.run(backend.shortest_path("a.py", "c.py"))
    assert len(edges) == 2
    assert edges[0].source == "a" and edges[0].target == "b"
    assert edges[1].source == "b" and edges[1].target == "c"


def test_shortest_path_no_match_returns_empty(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[{"id": "a", "label": "a.py"}],
        links=[],
    )
    backend = GraphifyRepositoryGraph(root=tmp_path, client=_client_with_files(tmp_path))
    assert asyncio.run(backend.shortest_path("a.py", "missing.py")) == []


def test_affected_filters_by_relation(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[
            {"id": "a", "label": "a.py"},
            {"id": "b", "label": "b.py"},
            {"id": "c", "label": "c.py"},
        ],
        links=[
            {"source": "a", "target": "a_target", "relation": "contains"},
            {"source": "b", "target": "a", "relation": "imports"},
            {"source": "c", "target": "a", "relation": "calls"},
        ],
    )
    # We need a target node, otherwise the reverse traversal is empty.
    _write_graph(  # overwrite with proper target
        tmp_path,
        nodes=[
            {"id": "a", "label": "a.py"},
            {"id": "b", "label": "b.py"},
            {"id": "c", "label": "c.py"},
            {"id": "a_target", "label": "target"},
        ],
        links=[
            {"source": "a", "target": "a_target", "relation": "contains"},
            {"source": "b", "target": "a", "relation": "imports"},
            {"source": "c", "target": "a", "relation": "calls"},
        ],
    )
    client = _client_with_files(tmp_path)
    backend = GraphifyRepositoryGraph(root=tmp_path, client=client)
    client.affected = AsyncMock(return_value="")  # type: ignore[method-assign]
    edges = asyncio.run(backend.affected("a.py", relation=["imports"], depth=2))
    sources = {(e.source, e.relation) for e in edges}
    assert ("b", "imports") in sources
    assert ("c", "calls") not in sources


def test_is_available_uses_client(tmp_path: Path) -> None:
    client = _client_with_files(tmp_path)
    backend = GraphifyRepositoryGraph(root=tmp_path, client=client)
    client.is_installed = AsyncMock(return_value=True)  # type: ignore[method-assign]
    assert asyncio.run(backend.is_available()) is True
    client.is_installed = AsyncMock(return_value=False)  # type: ignore[method-assign]
    assert asyncio.run(backend.is_available()) is False


def test_install_hint_contains_install_command() -> None:
    backend = GraphifyRepositoryGraph(root=Path("."))
    assert "uv tool install graphifyy" in asyncio.run(backend.install_hint())


def test_build_uses_client_and_caches_snapshot(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        nodes=[{"id": "a", "label": "a.py", "community": 0}],
        links=[],
    )
    client = _client_with_files(tmp_path)
    backend = GraphifyRepositoryGraph(root=tmp_path, client=client)

    from forgecli.graph.graphify import GraphifyBuildOutcome
    from forgecli.graph.repository import BuildResult

    outcome = GraphifyBuildOutcome(
        root=tmp_path,
        artifacts=GraphifyArtifacts.for_root(tmp_path),
        stdout="ok",
        stderr="",
    )
    client.build = AsyncMock(return_value=outcome)  # type: ignore[method-assign]
    result: BuildResult = asyncio.run(backend.build())
    assert isinstance(result, BuildResult)
    assert result.snapshot.node("a") is not None

    # Subsequent load() should reuse the cache.
    client.load_graph = lambda _p: {"nodes": [], "links": []}  # type: ignore[method-assign]
    snap = asyncio.run(backend.load())
    assert snap is result.snapshot
