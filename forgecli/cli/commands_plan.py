"""``forgecli plan`` and related subcommands.

The headline command is :func:`plan_cmd`, which takes a natural-language
goal and produces a full software plan: architecture, folder structure,
milestones, tasks, risks, and a prompt sequence for an AI agent.
"""

from __future__ import annotations

from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, success
from forgecli.planner.agent import Agent
from forgecli.planner.plan import Plan, Step
from forgecli.planner.planner import Planner
from forgecli.planner.render import print_plan
from forgecli.planner.serialize import plan_to_json, plan_to_markdown
from forgecli.planner.software import PlannerOptions, build_software_plan

app = typer.Typer(
    help="Turn a natural-language goal into a software plan.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# ---------------------------------------------------------------------------
# forge plan <goal>
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def plan_cmd(
    ctx: typer.Context,
    goal: str = typer.Argument(..., help="Natural-language description of the project."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print the plan as JSON instead of the Rich rendering.",
    ),
    md_output: bool = typer.Option(
        False,
        "--md",
        help="Print the plan as Markdown instead of the Rich rendering.",
    ),
    save: Path | None = typer.Option(
        None,
        "--save",
        help="Save the rendered plan to a file (use --md or --json to choose the format).",
    ),
    no_observability: bool = typer.Option(
        False,
        "--no-observability",
        help="Omit observability-related tasks and risks.",
    ),
    no_tests: bool = typer.Option(
        False,
        "--no-tests",
        help="Omit the test-coverage task from the final milestone.",
    ),
    max_milestones: int = typer.Option(
        6,
        "--max-milestones",
        help="Cap the number of milestones (default: 6).",
    ),
) -> None:
    """Build a software plan for ``goal`` and print it."""
    if ctx.invoked_subcommand is not None:
        return

    options = PlannerOptions(
        include_tests=not no_tests,
        include_observability=not no_observability,
        max_milestones=max_milestones,
    )
    plan = build_software_plan(goal, options)

    if save is not None:
        if json_output:
            target = save if save.suffix == ".json" else save.with_suffix(".json")
            target.write_text(plan_to_json(plan), encoding="utf-8")
            success(f"Plan saved to {target} (JSON).")
        elif md_output:
            target = save if save.suffix == ".md" else save.with_suffix(".md")
            target.write_text(plan_to_markdown(plan), encoding="utf-8")
            success(f"Plan saved to {target} (Markdown).")
        else:
            target = save if save.suffix == ".md" else save.with_suffix(".md")
            target.write_text(plan_to_markdown(plan), encoding="utf-8")
            success(f"Plan saved to {target} (Markdown).")

    if json_output:
        import sys

        sys.stdout.write(plan_to_json(plan))
        sys.stdout.write("\n")
        sys.stdout.flush()
    elif md_output:
        get_console().print(plan_to_markdown(plan), soft_wrap=False, highlight=False)
    else:
        print_plan(plan, console=get_console())


# ---------------------------------------------------------------------------
# forge plan run <goal>  (legacy: agent execution placeholder)
# ---------------------------------------------------------------------------


class _SingleShotPlanner(Planner):
    """A trivial planner that returns a single-step plan (placeholder)."""

    name = "single-shot"

    async def make_plan(self, goal: str, *, context=None) -> Plan:  # type: ignore[override]
        plan = Plan(name="single-shot", goal=goal)
        plan.add_step(Step(description=f"Achieve: {goal}", tool=None))
        return plan


@app.command("run")
def run(
    goal: str = typer.Argument(..., help="High-level goal to plan and execute."),
) -> None:
    """Run the legacy agent loop on ``goal`` (placeholder)."""
    import asyncio

    bootstrap_context()  # ensure wiring is exercised; kept for symmetry
    agent = Agent(planner=_SingleShotPlanner())
    plan = asyncio.run(agent.run(goal))
    get_console().print(f"Plan: {plan.name} ({len(plan.steps)} steps)")
    success("Planning complete (placeholder).")


__all__ = ["app"]
