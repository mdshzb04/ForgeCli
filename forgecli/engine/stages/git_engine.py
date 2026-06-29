"""Stage 8 — Git Engine (placeholder).

Stages, commits, and optionally pushes the applied changes. Currently
a pass-through that records intent; actual git integration will follow.
"""

from __future__ import annotations

from forgecli.engine.execution import StageContext, StageResult, StageStatus


class GitEngineStage:
    """Stage, commit, and push applied changes."""

    name = "git-engine"

    def __init__(self, auto_commit: bool = True) -> None:
        self._auto_commit = auto_commit

    async def __call__(self, context: StageContext) -> StageResult:
        if not context.engine.applied_files:
            return StageResult(
                status=StageStatus.SKIPPED,
                notes=("no files to commit",),
                data={"committed": False, "staged": False},
            )

        if not self._auto_commit:
            context.engine.extras["git_staged"] = True
            return StageResult(
                status=StageStatus.SUCCEEDED,
                notes=("auto-commit disabled; files ready to stage",),
                data={"committed": False, "staged": True},
            )

        context.engine.committed = True
        return StageResult(
            status=StageStatus.SUCCEEDED,
            notes=("commit recorded (placeholder)",),
            data={"committed": True, "staged": True},
        )
