"""Default pipeline composition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgecli.build import (
    BuildContext,
    BuildPipeline,
    PipelineStage,
)
from forgecli.build.apply import apply_diff
from forgecli.build.diff_extract import diff_extraction
from forgecli.build.llm import llm_call
from forgecli.build.optimize import ponytail_optimization
from forgecli.build.retrieval import graphify_retrieval
from forgecli.build.summarize import summarize
from forgecli.build.test_run import run_tests
from forgecli.optimizer.ponytail import PromptOptimizer
from forgecli.providers.base import Provider
from forgecli.providers.router import ModelRouter
from forgecli.providers.router_state import RouterState, load_state


def default_pipeline(
    *,
    provider: Provider,
    optimizer: PromptOptimizer | None,
    graph: Any | None = None,
    test_command: str | None = None,
    test_timeout: float = 120.0,
) -> BuildPipeline:
    """Construct the canonical pipeline."""
    stages: list[tuple[str, PipelineStage]] = [
        ("graphify-retrieval", _stage_with(graphify_retrieval, graph=graph)),
        ("ponytail-optimize", _stage_with(ponytail_optimization, optimizer=optimizer)),
        ("llm", _stage_with(llm_call, provider=provider)),
        ("diff-extract", diff_extraction),
        ("apply-diff", apply_diff),
        ("run-tests", _stage_with(run_tests, test_command=test_command, test_timeout=test_timeout)),
        ("summarize", summarize),
    ]
    return BuildPipeline(stages)


def _stage_with(
    stage: PipelineStage, **extras: Any
) -> PipelineStage:
    """Bind extras into a stage by closing over them."""
    async def _wrapped(context: BuildContext) -> BuildContext:
        context.extras.update(extras)
        return await stage(context)
    return _wrapped


def build_context_from(
    prompt: str,
    *,
    root: Path,
    router: ModelRouter | None = None,
    state: RouterState | None = None,
) -> BuildContext:
    """Build a :class:`BuildContext` with the router's decision pre-resolved."""
    state = state or RouterState()
    decision = (router or ModelRouter()).select(state.choice)
    return BuildContext(prompt=prompt, root=root, decision=decision)


__all__ = ["build_context_from", "default_pipeline"]


# Re-export helper for callers that want to load the persisted state too.
_ = load_state
