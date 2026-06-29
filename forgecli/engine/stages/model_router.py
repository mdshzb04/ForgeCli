"""Stage 5 — Model Router.

Resolves the user's model choice (or "auto") into a concrete
(provider, model) pair using :class:`ModelRouter`. The result
is stored in ``context.engine.model_selection``.
"""

from __future__ import annotations

from forgecli.engine.context import ModelSelection
from forgecli.engine.execution import StageContext, StageResult, StageStatus
from forgecli.providers.router import ModelCapabilities, ModelRouter
from forgecli.providers.router_state import RouterState, load_state


class ModelRouterStage:
    """Resolve the model choice and store the selection."""

    name = "model-router"

    def __init__(
        self,
        router: ModelRouter | None = None,
        state: RouterState | None = None,
    ) -> None:
        self._router = router or ModelRouter()
        self._state = state

    async def __call__(self, context: StageContext) -> StageResult:
        state = self._state or _resolve_state(context)
        choice = state.choice
        capabilities: ModelCapabilities = context.engine.extras.get(
            "model_capabilities", ModelCapabilities()
        )
        decision = self._router.select(choice, capabilities=capabilities)

        context.engine.model_selection = ModelSelection(
            provider=decision.provider_name,
            model=decision.model,
            mode=decision.mode.value,
            cost_in=decision.cost_in,
            cost_out=decision.cost_out,
        )
        context.engine.extras["decision"] = decision

        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "provider": decision.provider_name,
                "model": decision.model,
                "mode": decision.mode.value,
                "cost_in": decision.cost_in,
                "cost_out": decision.cost_out,
            },
            notes=(
                f"route: {decision.provider_name}/{decision.model} "
                f"(mode={decision.mode.value})",
            ),
        )


def _resolve_state(context: StageContext) -> RouterState:
    paths = context.engine.extras.get("paths")
    if paths is not None:
        return load_state(paths.data_dir / "router.json")
    return RouterState()
