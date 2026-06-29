"""Stage 6 — Execution Engine.

Invokes the LLM with the assembled prompt and extracts a unified diff
from the response. Combines :func:`forgecli.build.llm.llm_call` and
:func:`forgecli.build.diff_extract.diff_extraction` into a single stage.
"""

from __future__ import annotations

from pathlib import Path

from forgecli.build import BuildContext
from forgecli.build.diff_extract import diff_extraction
from forgecli.build.llm import llm_call
from forgecli.engine.execution import StageContext, StageResult, StageStatus
from forgecli.providers.base import Provider
from forgecli.providers.router import RouteDecision


class ExecutionEngineStage:
    """Send the prompt to the LLM and extract a diff."""

    name = "execution-engine"

    def __init__(self, provider: Provider | None = None) -> None:
        self._provider = provider

    async def __call__(self, context: StageContext) -> StageResult:
        provider = self._provider or context.engine.extras.get("provider")
        if provider is None:
            return StageResult(
                status=StageStatus.FAILED,
                error="no provider available for LLM call",
                notes=("no provider in extras or constructor",),
            )

        decision: RouteDecision | None = context.engine.extras.get("decision")
        build_ctx = BuildContext(
            prompt=context.engine.prompt,
            root=Path(context.engine.cwd),
            decision=decision,
        )
        if context.engine.retrieval is not None:
            build_ctx.retrieval = context.engine.retrieval.context_text
        if context.engine.optimized_request is not None:
            build_ctx.optimized_request = context.engine.optimized_request
            build_ctx.optimized_notes = context.engine.optimized_notes
        retries = int(context.engine.extras.get("retries", 0))
        build_ctx.extras["provider"] = provider
        build_ctx.extras["retries"] = retries

        build_ctx = await llm_call(build_ctx)
        build_ctx = await diff_extraction(build_ctx)

        context.engine.response = build_ctx.response
        context.engine.diff_text = build_ctx.diff_text

        diff_len = len(build_ctx.diff_text)
        notes: tuple[str, ...] = ()
        if diff_len > 0:
            notes = (f"extracted {diff_len}-char diff",)
        else:
            notes = ("no diff found in LLM response",)

        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "diff_length": diff_len,
                "has_response": build_ctx.response is not None,
            },
            notes=notes,
        )
