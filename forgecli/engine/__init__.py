"""The ForgeCLI Execution Engine.

This package defines the *contract* for every orchestration stage
in ForgeCLI. The pipeline is a fixed sequence of eight stages:

    1. Intent Analyzer        — turn the prompt into an Intent
    2. Repository Analyzer   — query Graphify for relevant context
    3. Context Optimizer     — apply Ponytail to the prompt + context
    4. Planning Engine       — produce a SoftwarePlan
    5. Model Router          — pick (provider, model) for the call
    6. Execution Engine      — invoke the LLM, extract a diff
    7. Validation Engine     — apply the diff + run tests + auto-fix
    8. Git Engine            — stage / commit / push the changes

Every stage is an independent object behind the :class:`Stage`
Protocol. The :class:`ExecutionEngine` runs them in order, emits
structured events, supports retries, cancellation, and plugin
hooks. No business logic lives in this package — the actual
implementations live in :mod:`forgecli.engine.stages` and may be
replaced by plugins.
"""

from forgecli.engine.context import (
    EngineContext,
    IntentAnalysis,
    ModelSelection,
    RetrievalResult,
    StageLog,
)
from forgecli.engine.defaults import (
    default_registry,
)
from forgecli.engine.events import (
    EngineCancelledError,
    EngineEvent,
    EventBus,
    LogLevel,
    ProgressEvent,
    StageEvent,
    TextLogEvent,
)
from forgecli.engine.execution import (
    EngineResult,
    ExecutionEngine,
    PipelineBuilder,
    Stage,
    StageContext,
    StageRegistry,
    StageResult,
    StageStatus,
)
from forgecli.engine.plugins import (
    EnginePluginFactory,
    HookManager,
    PluginHook,
    register_plugin,
    stage_as_plugin,
)
from forgecli.engine.stages import (
    ContextOptimizerStage,
    ExecutionEngineStage,
    GitEngineStage,
    IntentAnalyzerStage,
    ModelRouterStage,
    PlanningEngineStage,
    RepositoryAnalyzerStage,
    ValidationEngineStage,
)

__all__ = [
    "ContextOptimizerStage",
    "EngineCancelledError",
    "EngineContext",
    "EngineEvent",
    "EnginePluginFactory",
    "EngineResult",
    "EventBus",
    "ExecutionEngine",
    "ExecutionEngineStage",
    "GitEngineStage",
    "HookManager",
    "IntentAnalysis",
    "IntentAnalyzerStage",
    "LogLevel",
    "ModelRouterStage",
    "ModelSelection",
    "PipelineBuilder",
    "PlanningEngineStage",
    "PluginHook",
    "ProgressEvent",
    "RepositoryAnalyzerStage",
    "RetrievalResult",
    "Stage",
    "StageContext",
    "StageEvent",
    "StageLog",
    "StageRegistry",
    "StageResult",
    "StageStatus",
    "TextLogEvent",
    "ValidationEngineStage",
    "default_registry",
    "register_plugin",
    "stage_as_plugin",
]
