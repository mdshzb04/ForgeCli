"""Stage 2 — Ponytail optimization.

Wraps the user prompt with the configured :class:`PromptOptimizer`
(default: :class:`PonytailRulesetOptimizer`). The optimized request is
re-used by the LLM stage; the ruleset's notes are propagated to the
final summary.
"""

from __future__ import annotations

from forgecli.build import BuildContext
from forgecli.optimizer.ponytail import PromptOptimizer
from forgecli.providers.base import ChatMessage, ChatRequest, Role


async def ponytail_optimization(context: BuildContext) -> BuildContext:
    """Run the configured :class:`PromptOptimizer` and stash the result."""
    optimizer: PromptOptimizer | None = context.extras.get("optimizer")
    if optimizer is None:
        # No optimizer wired: produce a minimal request so downstream stages
        # always have something to consume.
        context.optimized_request = ChatRequest(
            messages=[ChatMessage(role=Role.USER, content=context.prompt)],
        )
        context.optimized_notes = ()
        return context

    request = ChatRequest(
        messages=[ChatMessage(role=Role.USER, content=context.prompt)],
    )
    optimized = await optimizer.optimize_chat(request)
    context.optimized_request = optimized.request
    context.optimized_notes = optimized.notes
    return context


__all__ = ["ponytail_optimization"]
