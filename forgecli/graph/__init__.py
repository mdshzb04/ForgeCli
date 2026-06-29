"""Repository graph: indexing, parsing, code intelligence.

The package exposes two layers:

* A small in-memory graph (:class:`CodeGraph`, :class:`Node`, :class:`Edge`)
  used by lightweight callers and tests.
* A back-end abstraction (:class:`RepositoryGraph`) implemented by
  :class:`GraphifyRepositoryGraph`, which delegates to the external
  Graphify CLI.
"""

from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
from forgecli.graph.edge import Edge, EdgeKind
from forgecli.graph.graph import CodeGraph
from forgecli.graph.graphify import (
    GraphifyArtifacts,
    GraphifyBuildOutcome,
    GraphifyClient,
    GraphifyInvocationError,
    GraphifyNotFoundError,
)
from forgecli.graph.indexer import Indexer
from forgecli.graph.node import Node, NodeKind
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

__all__ = [
    "BuildResult",
    "CodeGraph",
    "Edge",
    "EdgeKind",
    "ExplainResult",
    "GraphCommunity",
    "GraphEdge",
    "GraphNode",
    "GraphSnapshot",
    "GraphifyArtifacts",
    "GraphifyBuildOutcome",
    "GraphifyClient",
    "GraphifyInvocationError",
    "GraphifyNotFoundError",
    "GraphifyRepositoryGraph",
    "Indexer",
    "Node",
    "NodeKind",
    "QueryResult",
    "RepositoryGraph",
]
