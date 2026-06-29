"""Stage 4 — Planning Engine (placeholder).

Generates a software plan using :func:`forgecli.planner.software.build_software_plan`.
Stores the plan in ``context.engine.plan``.
"""

from __future__ import annotations

from forgecli.engine.execution import StageContext, StageResult, StageStatus
from forgecli.planner.software import PlannerOptions, build_software_plan


class PlanningEngineStage:
    """Generate a deterministic software plan from the prompt."""

    name = "planning-engine"

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    async def __call__(self, context: StageContext) -> StageResult:
        if not self._enabled:
            return StageResult(
                status=StageStatus.SKIPPED,
                notes=("planning disabled",),
                data={"skipped": True},
            )

        prompt = context.engine.prompt
        options = context.engine.extras.get("planner_options", PlannerOptions())
        plan = build_software_plan(prompt, options)
        context.engine.plan = plan

        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "summary": plan.summary,
                "milestones": len(plan.milestones),
                "tasks": len(plan.tasks) if hasattr(plan, "tasks") else 0,
            },
            notes=(
                f"plan: {plan.summary}",
                f"{len(plan.milestones)} milestones",
            ),
        )
