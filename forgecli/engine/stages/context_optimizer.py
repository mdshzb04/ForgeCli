"""Stage 3 — Context Optimizer.

Applies the Ponytail ruleset to the user prompt. Wraps
:func:`forgecli.build.optimize.ponytail_optimization`.
"""

from __future__ import annotations

from pathlib import Path

from forgecli.build import BuildContext
from forgecli.build.optimize import ponytail_optimization as _build_optimize
from forgecli.engine.execution import StageContext, StageResult, StageStatus
from forgecli.optimizer.ponytail import PromptOptimizer


class ContextOptimizerStage:
    """Optimize the prompt using Ponytail rules."""

    name = "context-optimizer"

    def __init__(self, optimizer: PromptOptimizer | None = None) -> None:
        self._optimizer = optimizer

    async def __call__(self, context: StageContext) -> StageResult:
        optimizer = self._optimizer or context.engine.extras.get("optimizer")
        build_ctx = BuildContext(
            prompt=context.engine.prompt,
            root=Path(context.engine.cwd),
        )
        build_ctx.extras["optimizer"] = optimizer

        build_ctx = await _build_optimize(build_ctx)

        context.engine.optimized_request = build_ctx.optimized_request
        context.engine.optimized_notes = build_ctx.optimized_notes

        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "notes": list(build_ctx.optimized_notes),
            },
            notes=build_ctx.optimized_notes or ("no optimization applied",),
        )
