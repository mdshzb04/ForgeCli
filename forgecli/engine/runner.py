"""High-level runner that wraps the ExecutionEngine for CLI use.

Provides :func:`run_engine` which accepts the same high-level
parameters as the CLI (prompt, provider, optimizer, graph, etc.)
and returns an :class:`EngineResult` ready for rendering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgecli.engine.context import EngineContext
from forgecli.engine.defaults import default_registry
from forgecli.engine.execution import EngineResult, ExecutionEngine, StageRegistry
from forgecli.engine.stages import (
    ContextOptimizerStage,
    ExecutionEngineStage,
    IntentAnalyzerStage,
    ModelRouterStage,
    RepositoryAnalyzerStage,
    ValidationEngineStage,
)


def run_engine(
    prompt: str,
    root: Path,
    *,
    provider: Any = None,
    optimizer: Any = None,
    graph: Any = None,
    classifier: Any = None,
    router: Any = None,
    test_command: str | None = None,
    test_timeout: float = 120.0,
    retries: int = 0,
    skip_tests: bool = False,
    skip_graph: bool = False,
    skip_ponytail: bool = False,
    pipeline_names: tuple[str, ...] | None = None,
    extras: dict[str, Any] | None = None,
) -> EngineResult:
    """Build an :class:`ExecutionEngine`, run the pipeline, and return the result.

    Parameters mirror the CLI flags; keyword arguments not consumed by
    this function are forwarded to :func:`default_registry`.

    Returns an :class:`EngineResult` that callers can render as text
    or JSON.
    """
    import asyncio

    engine_ctx = EngineContext(
        prompt=prompt,
        cwd=root,
    )
    if extras:
        engine_ctx.extras.update(extras)

    if not skip_graph and graph is not None:
        engine_ctx.extras["graph"] = graph
    if not skip_ponytail and optimizer is not None:
        engine_ctx.extras["optimizer"] = optimizer
    if provider is not None:
        engine_ctx.extras["provider"] = provider
    if retries:
        engine_ctx.extras["retries"] = retries
    if test_command is not None and not skip_tests:
        engine_ctx.extras["test_command"] = test_command
    engine_ctx.extras["test_timeout"] = test_timeout

    registry = default_registry(
        provider=provider,
        optimizer=optimizer if not skip_ponytail else None,
        graph=graph if not skip_graph else None,
        classifier=classifier,
        router=router,
        test_command=None if skip_tests else test_command,
    )

    names = pipeline_names or ExecutionEngine.DEFAULT_PIPELINE
    engine = ExecutionEngine.from_registry(registry, names=names)

    return asyncio.run(engine.run(engine_ctx))


def engine_result_to_dict(result: EngineResult) -> dict[str, object]:
    """Return a JSON-serializable view of an :class:`EngineResult`."""
    ctx = result.context
    return {
        "success": result.success,
        "cancelled": result.cancelled,
        "failed_stage": result.failed_stage,
        "error": result.error,
        "prompt": ctx.prompt,
        "run_id": ctx.run_id,
        "intent": ctx.intent_analysis.intent.value if ctx.intent_analysis else None,
        "intent_confidence": ctx.intent_analysis.confidence if ctx.intent_analysis else 0.0,
        "retrieval_match_count": len(ctx.retrieval.matched_nodes) if ctx.retrieval else 0,
        "model": ctx.model_selection.model if ctx.model_selection else None,
        "provider": ctx.model_selection.provider if ctx.model_selection else None,
        "diff_length": len(ctx.diff_text),
        "applied_files": [str(p) for p in ctx.applied_files],
        "test_returncode": ctx.test_returncode,
        "fix_attempts": ctx.fix_attempts,
        "committed": ctx.committed,
        "stages": [
            {
                "name": log.stage,
                "status": log.status,
                "duration_seconds": log.duration_seconds,
                "error": log.error,
            }
            for log in ctx.log
        ],
    }


def render_engine_result(result: EngineResult) -> str:
    """Return a human-readable summary of the engine run.

    Format is similar to the build pipeline's ``build_summary`` but
    reads from :class:`EngineContext` instead of :class:`BuildContext`.
    """
    ctx = result.context
    lines: list[str] = []
    lines.append(f"Goal: {ctx.prompt}")
    if ctx.model_selection is not None:
        ms = ctx.model_selection
        lines.append(
            f"Route: {ms.provider}/{ms.model} (mode={ms.mode}, "
            f"in=${ms.cost_in:.5f}/1k, out=${ms.cost_out:.5f}/1k)"
        )
    if ctx.optimized_notes:
        lines.append("Optimizer: " + ", ".join(ctx.optimized_notes))
    if ctx.applied_files:
        rel = [str(p.relative_to(ctx.cwd) if p.is_relative_to(ctx.cwd) else p) for p in ctx.applied_files]
        lines.append(f"Files touched ({len(rel)}):")
        for path in rel:
            lines.append(f"  - {path}")
    else:
        lines.append("Files touched: (none)")
    if ctx.test_returncode is None:
        lines.append("Tests: skipped")
    elif ctx.test_returncode == 0:
        lines.append("Tests: passed")
    else:
        lines.append(f"Tests: FAILED (exit {ctx.test_returncode})")
    total = sum(log.duration_seconds for log in ctx.log)
    lines.append(f"Total time: {total:.2f}s across {len(ctx.log)} stages")
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines)


__all__ = [
    "engine_result_to_dict",
    "render_engine_result",
    "run_engine",
]
