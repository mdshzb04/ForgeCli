"""Stage 2 — Repository Analyzer.

Queries the configured :class:`RepositoryGraph` for nodes relevant to
the user prompt. Wraps :func:`forgecli.build.retrieval.graphify_retrieval`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from forgecli.build import BuildContext
from forgecli.build.retrieval import graphify_retrieval as _build_retrieval
from forgecli.engine.context import RetrievalResult
from forgecli.engine.execution import StageContext, StageResult, StageStatus
from forgecli.graph.repository import RepositoryGraph


class RepositoryAnalyzerStage:
    """Query the repository graph for context relevant to the prompt."""

    name = "repository-analyzer"

    def __init__(self, graph: RepositoryGraph | None = None) -> None:
        self._graph = graph

    async def __call__(self, context: StageContext) -> StageResult:
        graph = self._graph or context.engine.extras.get("graph")
        build_ctx = BuildContext(
            prompt=context.engine.prompt,
            root=Path(context.engine.cwd),
        )
        build_ctx.extras["graph"] = graph

        started = time.perf_counter()
        build_ctx = await _build_retrieval(build_ctx)
        elapsed = time.perf_counter() - started

        context.engine.retrieval = RetrievalResult(
            query=context.engine.prompt,
            context_text=build_ctx.retrieval,
            notes=(
                f"retrieved in {elapsed:.3f}s",
                f"{len(build_ctx.retrieval)} chars",
            ),
        )
        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "retrieval_length": len(build_ctx.retrieval),
                "elapsed_seconds": round(elapsed, 3),
            },
            notes=(f"retrieved {len(build_ctx.retrieval)} chars of context",),
        )
