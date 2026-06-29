"""Serialize :class:`SoftwarePlan` to JSON or Markdown."""

from __future__ import annotations

from typing import Any

from forgecli.planner.software import SoftwarePlan


def plan_to_json(plan: SoftwarePlan, *, indent: int = 2) -> str:
    """Return a JSON string representation of ``plan``."""
    return plan.model_dump_json(indent=indent)


def plan_to_dict(plan: SoftwarePlan) -> dict[str, Any]:
    """Return the plan as a JSON-serializable dict."""
    return plan.model_dump(mode="json")


def plan_to_markdown(plan: SoftwarePlan) -> str:
    """Return a Markdown rendering of ``plan``."""
    parts: list[str] = []
    parts.append(f"# Plan: {plan.goal}\n")
    parts.append(f"_{plan.summary}_\n")

    parts.append("## Architecture\n")
    parts.append(plan.architecture.summary + "\n")
    parts.append("### Components\n")
    parts.append("| Name | Kind | Purpose | Depends on |")
    parts.append("| --- | --- | --- | --- |")
    for component in plan.architecture.components:
        deps = ", ".join(component.depends_on) or "—"
        parts.append(
            f"| {component.name} | {component.kind.value} | {component.purpose} | {deps} |"
        )
    parts.append("\n### Data flow\n")
    parts.append("| Source | Target | Contract |")
    parts.append("| --- | --- | --- |")
    for flow in plan.architecture.flows:
        parts.append(f"| {flow.source} | {flow.target} | {flow.contract} |")

    parts.append("\n## Folder structure\n")
    parts.append(f"Root: `{plan.folder_structure.root}/`\n")
    parts.append("```")
    for line in _format_tree(plan.folder_structure.tree):
        parts.append(line)
    parts.append("```")

    parts.append("\n## Roadmap\n")
    for milestone in plan.milestones:
        parts.append(
            f"### {milestone.id} — {milestone.title} ({milestone.priority.value})"
        )
        parts.append(milestone.description)
        parts.append("\n**Deliverables:**")
        for deliverable in milestone.deliverables:
            parts.append(f"- {deliverable}")

    parts.append("\n## Tasks\n")
    parts.append("| ID | M | Priority | Size | Title | Owner |")
    parts.append("| --- | --- | --- | --- | --- | --- |")
    for task in plan.tasks:
        parts.append(
            f"| {task.id} | {task.milestone_id} | {task.priority.value} | "
            f"{task.estimate} | {task.title} | {task.owner} |"
        )

    parts.append("\n## Risks\n")
    parts.append("| ID | Severity | Likelihood | Description | Mitigation |")
    parts.append("| --- | --- | --- | --- | --- |")
    for risk in plan.risks:
        parts.append(
            f"| {risk.id} | {risk.severity.value} | {risk.likelihood.value} | "
            f"{risk.description} | {risk.mitigation or '—'} |"
        )

    parts.append("\n## Prompt sequences\n")
    for sequence in plan.prompt_sequences:
        parts.append(f"### Task {sequence.task_id}\n")
        parts.append("**System**\n")
        parts.append(f"```\n{sequence.system}\n```\n")
        parts.append("**User**\n")
        parts.append(f"```\n{sequence.user}\n```\n")

    if plan.notes:
        parts.append("\n## Notes\n")
        for note in plan.notes:
            parts.append(f"- {note}")

    return "\n".join(parts) + "\n"


def _format_tree(nodes, prefix: str = "") -> list[str]:
    lines: list[str] = []
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        connector = "└── " if last else "├── "
        annotation = f"  ({node.purpose})" if node.purpose else ""
        lines.append(f"{prefix}{connector}{node.path}{annotation}")
        if node.children:
            extension = "    " if last else "│   "
            lines.extend(_format_tree(node.children, prefix + extension))
    return lines


__all__ = ["plan_to_dict", "plan_to_json", "plan_to_markdown"]
