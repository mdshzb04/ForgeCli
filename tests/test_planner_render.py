"""Tests for the Rich renderer and serialize for the software planner."""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from rich.theme import Theme

from forgecli.planner.render import print_plan, render_plan
from forgecli.planner.serialize import plan_to_dict, plan_to_json, plan_to_markdown
from forgecli.planner.software import build_software_plan

_THEME = Theme(
    {
        "info": "cyan",
        "warn": "yellow",
        "error": "bold red",
        "success": "bold green",
        "muted": "dim",
        "accent": "magenta",
        "accent.bold": "bold magenta",
    }
)


def _capture(plan) -> str:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=120,
        force_terminal=False,
        color_system=None,
        theme=_THEME,
    )
    print_plan(plan, console=console)
    return buffer.getvalue()


def test_render_plan_returns_a_list() -> None:
    plan = build_software_plan("Build a Python FastAPI service")
    sections = render_plan(plan)
    assert isinstance(sections, list)
    assert len(sections) > 0


def test_print_plan_does_not_crash() -> None:
    plan = build_software_plan("Build a CLI in Python")
    output = _capture(plan)
    assert "Forge Plan" in output
    assert "Build a CLI in Python" in output


def test_renderer_includes_all_milestone_titles() -> None:
    plan = build_software_plan("Build a Python API")
    output = _capture(plan)
    for milestone in plan.milestones:
        assert milestone.title in output


def test_renderer_includes_all_task_ids() -> None:
    plan = build_software_plan("Build a Python API")
    output = _capture(plan)
    for task in plan.tasks:
        assert task.id in output


def test_renderer_includes_folder_root() -> None:
    plan = build_software_plan("Build a Photo Sharing App")
    output = _capture(plan)
    assert "build-a-photo-sharing-app" in output


def test_renderer_prompts_are_limited_to_three() -> None:
    plan = build_software_plan("Build a Python API")
    output = _capture(plan)
    # First three task IDs are in the prompt section; the rest are summarized.
    sequence_ids = [s.task_id for s in plan.prompt_sequences]
    for tid in sequence_ids[:3]:
        assert tid in output
    if len(sequence_ids) > 3:
        assert "+ " in output  # the "...more" summary


def test_markdown_export_contains_sections() -> None:
    plan = build_software_plan("Build a Python API")
    md = plan_to_markdown(plan)
    assert "# Plan:" in md
    assert "## Architecture" in md
    assert "## Tasks" in md
    assert "## Risks" in md
    assert "## Prompt sequences" in md
    assert "| ID |" in md  # task table


def test_json_export_is_valid_json() -> None:
    plan = build_software_plan("Build a Python API")
    import json

    payload = json.loads(plan_to_json(plan))
    assert payload["goal"] == plan.goal
    assert isinstance(payload["milestones"], list)


def test_dict_export_round_trip() -> None:
    plan = build_software_plan("Build a Python API")
    d = plan_to_dict(plan)
    assert d == __import__("json").loads(plan_to_json(plan))


def test_renderer_handles_short_plan() -> None:
    """A plan with very few tasks should still render without error."""
    plan = build_software_plan("hi")
    output = _capture(plan)
    assert "Forge Plan" in output


# Silence unused import warning for symbols only used in some branches.
_ = pytest
