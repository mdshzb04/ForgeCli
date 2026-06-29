"""Plan/Step value types for the planner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class StepStatus(str, Enum):
    """Lifecycle status of a single :class:`Step`."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    """A unit of work in a :class:`Plan`."""

    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    tool: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    def mark_running(self) -> None:
        self.status = StepStatus.RUNNING
        self.started_at = time.time()

    def mark_done(self, *, result: Any = None, error: str | None = None) -> None:
        self.finished_at = time.time()
        if error is None:
            self.status = StepStatus.SUCCEEDED
        else:
            self.status = StepStatus.FAILED
            self.error = error
        self.result = result


@dataclass
class Plan:
    """An ordered, named collection of :class:`Step` objects."""

    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "plan"
    goal: str = ""
    steps: list[Step] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: Step) -> Step:
        self.steps.append(step)
        return step

    def pending_steps(self) -> list[Step]:
        return [s for s in self.steps if s.status is StepStatus.PENDING]
