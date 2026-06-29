"""Stage 1 — Graphify retrieval.

Asks the configured :class:`RepositoryGraph` to find nodes relevant to
the user prompt. The output is a compact text block listing the
matching node labels, files, and edges, which is fed into the LLM as
context in :mod:`forgecli.build.llm`.
"""

from __future__ import annotations

import re
from typing import Any

from forgecli.build import BuildContext
from forgecli.graph.repository import GraphNode, GraphSnapshot, RepositoryGraph


_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")
_FILE_LIKE_RE = re.compile(r"^[\w./-]+\.[A-Za-z0-9]+$")


async def graphify_retrieval(
    context: BuildContext, *, top_k: int = 8
) -> BuildContext:
    """Return a context with ``context.retrieval`` populated."""
    graph: RepositoryGraph | None = context.extras.get("graph")
    if graph is None:
        context.retrieval = ""
        return context

    try:
        snapshot = await graph.load()
    except Exception as exc:  # noqa: BLE001
        context.retrieval = f"[graph: failed to load ({exc!r})]"
        return context

    matches = _rank_nodes(snapshot, context.prompt, limit=top_k)
    if not matches:
        context.retrieval = "[graph: no matches]"
        return context

    lines = ["[graph retrieval]"]
    for node, _score in matches:
        location = (
            f" ({node.source_file}:{node.source_location})"
            if node.source_file
            else ""
        )
        lines.append(f"- {node.label}{location}")
    context.retrieval = "\n".join(lines)
    return context


def _rank_nodes(
    snapshot: GraphSnapshot, query: str, *, limit: int
) -> list[tuple[GraphNode, int]]:
    """Return the top ``limit`` nodes most relevant to ``query``.

    Scoring is intentionally simple and deterministic: each token in
    ``query`` contributes one point for every node whose label or
    source file contains the token as a substring. Tokens that look
    like filenames (``foo.py``, ``auth/bar.ts``) get a bonus when
    they match a node's ``source_file`` exactly.
    """
    tokens = [tok.lower() for tok in _TOKEN_RE.findall(query or "")]
    if not tokens:
        return []
    scored: list[tuple[GraphNode, int]] = []
    for node in snapshot.nodes:
        label = (node.label or "").lower()
        source = (node.source_file or "").lower()
        if not label and not source:
            continue
        score = 0
        for token in tokens:
            if token and token in label:
                score += 1
            if token and token in source:
                score += 1
            if (
                _FILE_LIKE_RE.match(token)
                and node.source_file
                and token == node.source_file.lower()
            ):
                score += 3
        if score > 0:
            scored.append((node, score))
    scored.sort(key=lambda pair: (pair[1], pair[0].label), reverse=True)
    return scored[:limit]


__all__ = ["graphify_retrieval"]


_ = Any  # keep typing.Any referenced for the test-only type hints
