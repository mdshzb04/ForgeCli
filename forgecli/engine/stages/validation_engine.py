"""Stage 7 — Validation Engine.

Applies the extracted diff to disk, runs tests, and produces a
summary of the results. Combines :func:`forgecli.build.apply.apply_diff`,
:func:`forgecli.build.test_run.run_tests`, and
:func:`forgecli.build.summarize.summarize` into a single stage.
"""

from __future__ import annotations

from pathlib import Path

from forgecli.build import BuildContext
from forgecli.build.apply import apply_diff
from forgecli.build.summarize import summarize
from forgecli.build.test_run import run_tests
from forgecli.engine.execution import StageContext, StageResult, StageStatus


class ValidationEngineStage:
    """Apply the diff, run tests, and produce a summary."""

    name = "validation-engine"

    def __init__(self, test_command: str | None = None) -> None:
        self._test_command = test_command

    async def __call__(self, context: StageContext) -> StageResult:
        decision = context.engine.extras.get("decision")
        build_ctx = BuildContext(
            prompt=context.engine.prompt,
            root=Path(context.engine.cwd),
            decision=decision,
        )
        build_ctx.diff_text = context.engine.diff_text
        if context.engine.retrieval is not None:
            build_ctx.retrieval = context.engine.retrieval.context_text

        test_command = (
            self._test_command or context.engine.extras.get("test_command")
        )
        if test_command:
            build_ctx.extras["test_command"] = test_command
        test_timeout = context.engine.extras.get("test_timeout")
        if test_timeout:
            build_ctx.extras["test_timeout"] = test_timeout

        build_ctx = await apply_diff(build_ctx)
        build_ctx = await run_tests(build_ctx)
        build_ctx = await summarize(build_ctx)

        context.engine.applied_files = build_ctx.applied_files
        context.engine.diff_text = build_ctx.diff_text
        context.engine.test_stdout = build_ctx.test_stdout
        context.engine.test_stderr = build_ctx.test_stderr
        context.engine.test_returncode = build_ctx.test_returncode
        context.engine.extras["summary"] = build_ctx.summary

        notes: list[str] = []
        if build_ctx.applied_files:
            notes.append(f"applied {len(build_ctx.applied_files)} files")
        else:
            notes.append("no files applied")

        if build_ctx.test_returncode is None:
            notes.append("tests skipped")
        elif build_ctx.test_returncode == 0:
            notes.append("tests passed")
        else:
            notes.append(f"tests FAILED (exit {build_ctx.test_returncode})")
            return StageResult(
                status=StageStatus.FAILED,
                data={
                    "applied_files": [str(p) for p in build_ctx.applied_files],
                    "test_returncode": build_ctx.test_returncode,
                    "test_stderr": build_ctx.test_stderr[-500:],
                },
                notes=tuple(notes),
                error=f"tests failed with exit code {build_ctx.test_returncode}",
            )

        return StageResult(
            status=StageStatus.SUCCEEDED,
            data={
                "applied_files": [str(p) for p in build_ctx.applied_files],
                "test_returncode": build_ctx.test_returncode,
            },
            notes=tuple(notes),
        )
