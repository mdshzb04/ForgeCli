"""Concrete Stage implementations for the Execution Engine.

Each module in this package implements one or more :class:`Stage`
protocol objects that wire into the engine's
:attr:`~forgecli.engine.execution.ExecutionEngine.DEFAULT_PIPELINE`.

Stages are thin adapters over the existing build pipeline functions
in :mod:`forgecli.build` — they map between :class:`EngineContext`
and :class:`BuildContext`, then delegate to the well-tested build
functions.
"""

from forgecli.engine.stages.context_optimizer import ContextOptimizerStage
from forgecli.engine.stages.execution_engine_stage import ExecutionEngineStage
from forgecli.engine.stages.git_engine import GitEngineStage
from forgecli.engine.stages.intent_analyzer import IntentAnalyzerStage
from forgecli.engine.stages.model_router import ModelRouterStage
from forgecli.engine.stages.planning_engine import PlanningEngineStage
from forgecli.engine.stages.repository_analyzer import RepositoryAnalyzerStage
from forgecli.engine.stages.validation_engine import ValidationEngineStage

__all__ = [
    "ContextOptimizerStage",
    "ExecutionEngineStage",
    "GitEngineStage",
    "IntentAnalyzerStage",
    "ModelRouterStage",
    "PlanningEngineStage",
    "RepositoryAnalyzerStage",
    "ValidationEngineStage",
]
