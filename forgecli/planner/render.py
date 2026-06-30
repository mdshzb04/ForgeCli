"""Rich-based renderer for :class:`SoftwarePlan`.

The renderer is pure: it accepts a :class:`SoftwarePlan` and a Rich
:class:`Console` and emits the plan as a sequence of sections. Callers
can override the console, choose a different layout, or post-process
the output before display.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from forgecli.planner.software import (
    FolderNode,
    Priority,
    RiskSeverity,
    SoftwarePlan,
)

_PRIORITY_STYLE: dict[Priority, str] = {
    Priority.P0: "bold red",
    Priority.P1: "bold yellow",
    Priority.P2: "cyan",
    Priority.P3: "muted",
}

_RISK_STYLE: dict[RiskSeverity, str] = {
    RiskSeverity.LOW: "green",
    RiskSeverity.MEDIUM: "yellow",
    RiskSeverity.HIGH: "bold red",
}


def print_plan(plan: SoftwarePlan, console: Console | None = None) -> None:
    """Print a :class:`SoftwarePlan` using the given Rich console."""
    console = console or Console()
    for renderable in render_plan(plan):
        console.print(renderable)


def render_plan(plan: SoftwarePlan) -> list:
    """Return a list of Rich renderables that visualize ``plan``."""
    renderables: list = []
    renderables.append(_render_header(plan))
    renderables.append(_render_summary(plan))
    renderables.append(_render_architecture(plan))
    renderables.append(_render_folder_structure(plan))
    renderables.append(_render_milestones(plan))
    renderables.append(_render_tasks(plan))
    renderables.append(_render_risks(plan))
    renderables.extend(_render_prompt_sequences(plan))
    if plan.notes:
        renderables.append(_render_notes(plan))
    return renderables


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _render_header(plan: SoftwarePlan) -> Panel:
    title = Text("Forge Plan", style="bold accent")
    title.append("  —  ", style="muted")
    title.append(plan.goal, style="bold")
    return Panel(
        title,
        border_style="magenta",
        title=Text("forge plan", style="bold magenta"),
        title_align="left",
        padding=(0, 1),
    )


def _render_summary(plan: SoftwarePlan) -> Panel:
    body = Text(plan.summary, style="white")
    stats = Table.grid(padding=(0, 2))
    stats.add_column(style="bold")
    stats.add_column()
    stats.add_row("milestones", str(len(plan.milestones)))
    stats.add_row("tasks", str(len(plan.tasks)))
    stats.add_row("risks", str(len(plan.risks)))
    stats.add_row("prompts", str(len(plan.prompt_sequences)))
    layout = Group(
        body,
        Text(""),
        stats,
    )
    return Panel(layout, title="Summary", border_style="cyan", padding=(0, 1))


def _render_architecture(plan: SoftwarePlan) -> Panel:
    table = Table(
        title="Components",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    table.add_column("Name", style="bold")
    table.add_column("Kind")
    table.add_column("Purpose", overflow="fold")
    table.add_column("Depends on", style="muted")
    for component in plan.architecture.components:
        table.add_row(
            component.name,
            component.kind.value,
            component.purpose,
            ", ".join(component.depends_on) or "—",
        )
    flows = Table(
        title="Data flow",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    flows.add_column("Source", style="bold")
    flows.add_column("Target", style="bold")
    flows.add_column("Contract", overflow="fold")
    for flow in plan.architecture.flows:
        flows.add_row(flow.source, flow.target, flow.contract)
    body: list = [
        Text(plan.architecture.summary, style="white"),
        Text(""),
        table,
        Text(""),
        flows,
    ]
    return Panel(
        Group(*body), title="Architecture", border_style="cyan", padding=(0, 1)
    )


def _render_folder_structure(plan: SoftwarePlan) -> Panel:
    root = plan.folder_structure.root
    tree = Tree(Text(root, style="bold magenta"), guide_style="cyan")
    _populate_tree(tree, plan.folder_structure.tree)
    return Panel(
        tree, title=f"Folder structure ({root}/)", border_style="cyan", padding=(0, 1)
    )


def _populate_tree(parent: Tree, nodes: list[FolderNode]) -> None:
    for node in nodes:
        label = Text(node.path, style="bold")
        if node.purpose:
            label.append("  ")
            label.append(Text(f"({node.purpose})", style="muted"))
        branch = parent.add(label)
        if node.children:
            _populate_tree(branch, node.children)


def _render_milestones(plan: SoftwarePlan) -> Panel:
    table = Table(
        title="Milestones",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Priority", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Description", overflow="fold")
    table.add_column("Tasks", justify="right", style="muted")
    for milestone in plan.milestones:
        table.add_row(
            milestone.id,
            Text(milestone.priority.value, style=_PRIORITY_STYLE[milestone.priority]),
            milestone.title,
            milestone.description,
            str(len(milestone.task_ids)),
        )
    return Panel(table, title="Roadmap", border_style="cyan", padding=(0, 1))


def _render_tasks(plan: SoftwarePlan) -> Panel:
    table = Table(
        title="Tasks",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=True,
        expand=True,
    )
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("M", no_wrap=True, style="muted")
    table.add_column("Priority", no_wrap=True)
    table.add_column("Size", no_wrap=True, justify="right")
    table.add_column("Title", style="bold")
    table.add_column("Acceptance", overflow="fold", style="muted")
    for task in plan.tasks:
        acceptance = "\n".join(f"• {c}" for c in task.acceptance) or "—"
        table.add_row(
            task.id,
            task.milestone_id,
            Text(task.priority.value, style=_PRIORITY_STYLE[task.priority]),
            task.estimate,
            task.title,
            acceptance,
        )
    return Panel(table, title="Task list", border_style="cyan", padding=(0, 1))


def _render_risks(plan: SoftwarePlan) -> Panel:
    table = Table(
        title="Risks",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=True,
        expand=True,
    )
    table.add_column("ID", style="bold", no_wrap=True)
    table.add_column("Severity", no_wrap=True)
    table.add_column("Likelihood", no_wrap=True)
    table.add_column("Description", overflow="fold")
    table.add_column("Mitigation", overflow="fold", style="muted")
    for risk in plan.risks:
        table.add_row(
            risk.id,
            Text(risk.severity.value, style=_RISK_STYLE[risk.severity]),
            Text(risk.likelihood.value, style=_RISK_STYLE[risk.likelihood]),
            risk.description,
            risk.mitigation or "—",
        )
    return Panel(table, title="Risk register", border_style="cyan", padding=(0, 1))


def _render_prompt_sequences(plan: SoftwarePlan) -> list[Panel]:
    panels: list[Panel] = []
    for sequence in plan.prompt_sequences[:3]:
        body = Text()
        body.append("system: ", style="bold magenta")
        body.append(sequence.system, style="white")
        body.append("\n\n")
        body.append("user: ", style="bold cyan")
        body.append(sequence.user, style="white")
        panels.append(
            Panel(
                body,
                title=f"Prompt — task {sequence.task_id}",
                border_style="magenta",
                padding=(0, 1),
            )
        )
    remaining = len(plan.prompt_sequences) - 3
    if remaining > 0:
        panels.append(
            Panel(
                Text(
                    f"+ {remaining} more prompt sequences (use --json or --md to view all).",
                    style="muted",
                ),
                border_style="magenta",
                padding=(0, 1),
            )
        )
    return panels


def _render_notes(plan: SoftwarePlan) -> Panel:
    body = Text("\n".join(f"• {note}" for note in plan.notes), style="muted")
    return Panel(body, title="Notes", border_style="cyan", padding=(0, 1))


__all__ = ["print_plan", "render_plan"]
