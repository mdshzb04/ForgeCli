"""Tests for the software planner."""

from __future__ import annotations

import json

import pytest

from forgecli.planner.serialize import plan_to_dict, plan_to_json, plan_to_markdown
from forgecli.planner.software import (
    PlannerOptions,
    Priority,
    SoftwarePlan,
    build_software_plan,
)


def _default_plan() -> SoftwarePlan:
    return build_software_plan(
        "Build a Python FastAPI service for user authentication"
    )


def test_plan_contains_all_sections() -> None:
    plan = _default_plan()
    assert plan.architecture.components
    assert plan.architecture.flows
    assert plan.folder_structure.tree
    assert plan.milestones
    assert plan.tasks
    assert plan.risks
    assert plan.prompt_sequences


def test_goal_round_trips() -> None:
    plan = _default_plan()
    assert "FastAPI" in plan.goal
    assert plan.summary


def test_milestones_capped() -> None:
    plan = build_software_plan("Build a CLI", PlannerOptions(max_milestones=3))
    assert len(plan.milestones) == 3


def test_observability_omitted_when_disabled() -> None:
    plan = build_software_plan(
        "Build a Python API", PlannerOptions(include_observability=False)
    )
    titles = " ".join(t.title for t in plan.tasks)
    assert "metrics" not in titles.lower()
    # Risks tied to observability should be omitted too.
    descriptions = " ".join(r.description for r in plan.risks)
    assert "observability" not in descriptions.lower()


def test_tests_omitted_when_disabled() -> None:
    plan = build_software_plan(
        "Build a Python API", PlannerOptions(include_tests=False)
    )
    titles = " ".join(t.title for t in plan.tasks)
    assert "coverage" not in titles.lower()


def test_architecture_components_have_unique_names() -> None:
    plan = _default_plan()
    names = [c.name for c in plan.architecture.components]
    assert len(names) == len(set(names))


def test_dependencies_chain_within_milestone() -> None:
    from itertools import pairwise

    plan = _default_plan()
    for milestone in plan.milestones:
        ids = milestone.task_ids
        if len(ids) < 2:
            continue
        for prev_id, current_id in pairwise(ids):
            current = next(t for t in plan.tasks if t.id == current_id)
            assert prev_id in current.depends_on


def test_every_task_has_a_milestone() -> None:
    plan = _default_plan()
    milestone_ids = {m.id for m in plan.milestones}
    for task in plan.tasks:
        assert task.milestone_id in milestone_ids


def test_prompt_sequences_cover_every_task() -> None:
    plan = _default_plan()
    sequence_ids = {s.task_id for s in plan.prompt_sequences}
    for task in plan.tasks:
        assert task.id in sequence_ids


def test_prompt_sequences_reference_task_acceptance() -> None:
    plan = _default_plan()
    for sequence in plan.prompt_sequences:
        task = next(t for t in plan.tasks if t.id == sequence.task_id)
        if task.acceptance:
            assert task.acceptance[0][:30] in sequence.user


def test_classify_goal_chooses_api_for_known_keyword() -> None:
    plan = build_software_plan("Build a REST API for invoicing")
    # The architecture summary mentions "API" or "interface" component.
    text = plan.architecture.summary.lower()
    assert "api" in text or "interface" in text


def test_detect_stack_recognizes_python_fastapi() -> None:
    plan = build_software_plan("Build a FastAPI service in Python")
    components = [c.purpose for c in plan.architecture.components]
    # The architecture summary mentions python/fastapi somewhere.
    blob = " ".join([*components, plan.summary, plan.architecture.summary]).lower()
    assert "python" in blob or "fastapi" in blob


def test_detect_stack_falls_back_to_python() -> None:
    plan = build_software_plan("Build a thingamajig")
    blob = (plan.summary + " " + plan.architecture.summary).lower()
    assert "python" in blob


def test_folder_structure_uses_slugified_root() -> None:
    plan = build_software_plan("Build a Photo Sharing App")
    assert plan.folder_structure.root == "build-a-photo-sharing-app"


def test_risks_have_unique_ids() -> None:
    plan = _default_plan()
    risk_ids = [r.id for r in plan.risks]
    assert len(risk_ids) == len(set(risk_ids))


def test_api_goal_includes_auth_risk() -> None:
    plan = build_software_plan("Build an API")
    risk_text = " ".join(r.description for r in plan.risks).lower()
    assert "auth" in risk_text or "authentication" in risk_text


def test_build_software_plan_rejects_empty_goal() -> None:
    with pytest.raises(ValueError):
        build_software_plan("   ")


def test_to_json_round_trips() -> None:
    plan = _default_plan()
    payload = plan_to_json(plan)
    parsed = json.loads(payload)
    assert parsed["goal"] == plan.goal
    assert isinstance(parsed["milestones"], list)
    assert isinstance(parsed["prompt_sequences"], list)


def test_to_dict_matches_to_json() -> None:
    plan = _default_plan()
    assert plan_to_dict(plan) == json.loads(plan_to_json(plan))


def test_to_markdown_includes_all_sections() -> None:
    plan = _default_plan()
    md = plan_to_markdown(plan)
    assert "# Plan:" in md
    assert "## Architecture" in md
    assert "## Folder structure" in md
    assert "## Roadmap" in md
    assert "## Tasks" in md
    assert "## Risks" in md
    assert "## Prompt sequences" in md
    assert "FastAPI" in plan.goal


def test_prompt_sequence_user_includes_task_title() -> None:
    plan = _default_plan()
    for sequence in plan.prompt_sequences:
        task = next(t for t in plan.tasks if t.id == sequence.task_id)
        assert task.title in sequence.user


def test_priority_distribution() -> None:
    plan = _default_plan()
    priorities = {task.priority for task in plan.tasks}
    # At least P0 and P1 should be present.
    assert Priority.P0 in priorities
    assert Priority.P1 in priorities


def test_folder_node_is_recursive() -> None:
    plan = _default_plan()
    src = next(
        node for node in plan.folder_structure.tree if node.path == "src"
    )
    assert any(child.children for child in src.children) or src.children
