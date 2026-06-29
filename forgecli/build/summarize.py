"""Stage 7 — summarize.

Composes a short human-readable summary of the run. The summary is
shown in the terminal and stored in ``context.summary``.
"""

from __future__ import annotations

import time

from forgecli.build import BuildContext, BuildResult, StageStatus


def build_summary(context: BuildContext) -> str:
    """Return a multi-line summary of the run."""
    lines: list[str] = []
    lines.append(f"Goal: {context.prompt}")
    if context.decision is not None:
        d = context.decision
        lines.append(
            f"Route: {d.provider_name}/{d.model} "
            f"(mode={d.mode.value}, "
            f"in=${d.cost_in:.5f}/1k, out=${d.cost_out:.5f}/1k)"
        )
    if context.optimized_notes:
        lines.append("Optimizer: " + ", ".join(context.optimized_notes))
    if context.applied_files:
        rel = [str(p.relative_to(context.root)) for p in context.applied_files]
        lines.append(f"Files touched ({len(rel)}):")
        for path in rel:
            lines.append(f"  - {path}")
    else:
        lines.append("Files touched: (none)")
    if context.test_returncode is None:
        lines.append("Tests: skipped (no test runner available)")
    elif context.test_returncode == 0:
        lines.append("Tests: passed")
    else:
        lines.append(f"Tests: FAILED (exit {context.test_returncode})")
        if context.test_stderr.strip():
            lines.append("--- stderr ---")
            lines.append(context.test_stderr.strip())
    total = sum(s.duration_seconds or 0.0 for s in context.stages)
    lines.append(f"Total time: {total:.2f}s across {len(context.stages)} stages")
    return "\n".join(lines)


async def summarize(context: BuildContext) -> BuildContext:
    """Populate ``context.summary`` with a human-readable overview."""
    context.summary = build_summary(context)
    return context


def result_to_dict(result: BuildResult) -> dict[str, object]:
    """Return a JSON-serializable view of the result (for --json output)."""
    return {
        "success": result.success,
        "failure_stage": result.failure_stage,
        "summary": result.context.summary,
        "applied_files": [str(p) for p in result.context.applied_files],
        "test_returncode": result.context.test_returncode,
        "stages": [
            {
                "name": s.name,
                "status": s.status.value,
                "duration_seconds": s.duration_seconds,
                "notes": list(s.notes),
                "error": s.error,
            }
            for s in result.context.stages
        ],
    }


__all__ = ["build_summary", "result_to_dict", "summarize"]


# Silence unused-import warnings for symbols only used in some branches.
_ = StageStatus
_ = time
