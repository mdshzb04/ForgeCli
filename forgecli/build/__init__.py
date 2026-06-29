"""Build pipeline: Graphify retrieval -> Ponytail -> LLM -> diff -> apply -> test -> summary.

Each stage is a small async function that takes a :class:`BuildContext` and
mutates it, returning the same context. The :class:`BuildPipeline` runs the
stages in order and records per-stage status; on failure it short-circuits
unless ``continue_on_error`` is set.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from forgecli.providers.base import ChatResponse
from forgecli.providers.router import RouteDecision


class StageStatus(str, Enum):
    """Lifecycle status of a single pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageRecord:
    """One row in the pipeline's per-stage log."""

    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    notes: tuple[str, ...] = ()
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass
class BuildContext:
    """Mutable state shared by every pipeline stage."""

    prompt: str
    root: Path
    decision: RouteDecision | None = None
    retrieval: str = ""               # graph-derived context
    optimized_request: Any = None
    optimized_notes: tuple[str, ...] = ()
    response: ChatResponse | None = None
    diff_text: str = ""
    applied_files: list[Path] = field(default_factory=list)
    test_stdout: str = ""
    test_stderr: str = ""
    test_returncode: int | None = None
    summary: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
    stages: list[StageRecord] = field(default_factory=list)


PipelineStage = Callable[[BuildContext], Awaitable[BuildContext]]


@dataclass
class BuildResult:
    """The output of :meth:`BuildPipeline.run`."""

    success: bool
    context: BuildContext
    failure_stage: str | None = None


class BuildPipeline:
    """A composable async pipeline of named stages."""

    def __init__(
        self,
        stages: list[tuple[str, PipelineStage]],
        *,
        continue_on_error: bool = False,
    ) -> None:
        self._stages = list(stages)
        self._continue_on_error = continue_on_error

    @property
    def stage_names(self) -> list[str]:
        return [name for name, _ in self._stages]

    async def run(self, context: BuildContext) -> BuildResult:
        context.stages = [
            StageRecord(name=name) for name, _ in self._stages
        ]
        for index, (name, stage) in enumerate(self._stages):
            record = context.stages[index]
            record.status = StageStatus.RUNNING
            import time

            record.started_at = time.perf_counter()
            try:
                context = await stage(context)
                record.status = StageStatus.SUCCEEDED
            except Exception as exc:  # noqa: BLE001 - we want to capture everything
                record.status = StageStatus.FAILED
                record.error = repr(exc)
                record.finished_at = time.perf_counter()
                if not self._continue_on_error:
                    return BuildResult(
                        success=False,
                        context=context,
                        failure_stage=name,
                    )
            else:
                record.finished_at = time.perf_counter()
        return BuildResult(success=True, context=context)


__all__ = [
    "BuildContext",
    "BuildPipeline",
    "BuildResult",
    "PipelineStage",
    "StageRecord",
    "StageStatus",
]
