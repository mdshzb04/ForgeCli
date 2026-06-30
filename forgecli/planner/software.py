"""Software planner: turn a natural-language goal into a full plan.

The output is a :class:`SoftwarePlan` — a structured, fully-typed
breakdown of the goal into:

* **architecture** — components, contracts, data flow;
* **folder structure** — the directory layout the project will use;
* **milestones** — coarse-grained phases with deliverables;
* **tasks** — fine-grained actionable units (linked to milestones);
* **risks** — known unknowns, mitigations;
* **prompt sequence** — the system + user prompts an agent would feed
  to a model to execute each task.

The planner is intentionally rule-based and deterministic so it can
run offline and be tested without network access. A future
implementation can swap in an LLM-driven planner by re-implementing
:func:`build_software_plan`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


class RiskSeverity(str, Enum):
    """Severity assigned to a single :class:`Risk`."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComponentKind(str, Enum):
    """Role a component plays in the architecture."""

    API = "api"
    UI = "ui"
    WORKER = "worker"
    DATA = "data"
    INFRA = "infra"
    LIBRARY = "library"
    CLI = "cli"
    SERVICE = "service"


class TaskStatus(str, Enum):
    """Lifecycle status of a single :class:`Task`."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class Priority(str, Enum):
    """Priority assigned to a milestone or task."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


# ---------------------------------------------------------------------------
# Plan schema
# ---------------------------------------------------------------------------


class Component(BaseModel):
    """A logical component of the architecture."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: ComponentKind
    purpose: str
    depends_on: tuple[str, ...] = Field(default_factory=tuple)


class DataFlow(BaseModel):
    """A directed edge in the architecture diagram."""

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    contract: str


class Architecture(BaseModel):
    """The architecture section of a :class:`SoftwarePlan`."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    components: list[Component] = Field(default_factory=list)
    flows: list[DataFlow] = Field(default_factory=list)


class FolderNode(BaseModel):
    """A single node in the project tree."""

    model_config = ConfigDict(extra="forbid")

    path: str
    purpose: str = ""
    children: list[FolderNode] = Field(default_factory=list)


FolderNode.model_rebuild()


class FolderStructure(BaseModel):
    """The folder-structure section of a :class:`SoftwarePlan`."""

    model_config = ConfigDict(extra="forbid")

    root: str
    tree: list[FolderNode] = Field(default_factory=list)


class Milestone(BaseModel):
    """A coarse-grained phase of the implementation roadmap."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    priority: Priority = Priority.P1
    deliverables: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)


class Task(BaseModel):
    """A fine-grained actionable unit of work."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    milestone_id: str
    priority: Priority = Priority.P1
    estimate: str = "M"          # S / M / L / XL
    status: TaskStatus = TaskStatus.PLANNED
    owner: str = "agent"
    acceptance: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class Risk(BaseModel):
    """A known unknown."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    severity: RiskSeverity = RiskSeverity.MEDIUM
    likelihood: RiskSeverity = RiskSeverity.MEDIUM
    mitigation: str = ""


class PromptTurn(BaseModel):
    """A single (role, content) pair to be fed to a model."""

    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class PromptSequence(BaseModel):
    """The prompt sequence for a single task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    system: str
    user: str
    turns: list[PromptTurn] = Field(default_factory=list)


class SoftwarePlan(BaseModel):
    """A complete software plan derived from a natural-language goal."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    summary: str
    architecture: Architecture
    folder_structure: FolderStructure
    milestones: list[Milestone] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    prompt_sequences: list[PromptSequence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------


_KEYWORD_GOALS: dict[str, str] = {
    "api": "an HTTP API",
    "backend": "a backend service",
    "frontend": "a frontend application",
    "cli": "a command-line tool",
    "library": "a reusable library",
    "sdk": "a software development kit",
    "service": "a backend service",
    "worker": "an async worker",
    "pipeline": "a data pipeline",
    "dashboard": "a web dashboard",
    "chatbot": "a chatbot",
    "agent": "an agentic system",
    "scraper": "a web scraper",
    "scheduler": "a job scheduler",
    "bot": "a bot",
    "mobile": "a mobile application",
    "app": "an application",
}


_STACK_HINTS: dict[str, tuple[str, ...]] = {
    "python": ("Python", "FastAPI", "SQLAlchemy", "PostgreSQL", "pytest"),
    "fastapi": ("Python", "FastAPI", "Pydantic", "PostgreSQL"),
    "django": ("Python", "Django", "PostgreSQL"),
    "flask": ("Python", "Flask", "SQLite"),
    "typescript": ("TypeScript", "Node.js", "Express", "Vitest"),
    "javascript": ("JavaScript", "Node.js", "Express"),
    "react": ("TypeScript", "React", "Vite", "Vitest"),
    "next": ("TypeScript", "Next.js", "React", "Vitest"),
    "node": ("TypeScript", "Node.js", "Express", "Vitest"),
    "go": ("Go", "net/http", "PostgreSQL", "go test"),
    "rust": ("Rust", "Tokio", "PostgreSQL", "cargo test"),
    "java": ("Java", "Spring Boot", "Maven", "JUnit"),
    "kotlin": ("Kotlin", "Spring Boot", "Gradle", "JUnit"),
    "swift": ("Swift", "SwiftUI", "XCTest"),
    "ruby": ("Ruby", "Rails", "PostgreSQL", "RSpec"),
    "elixir": ("Elixir", "Phoenix", "PostgreSQL", "ExUnit"),
}


_DEFAULT_MILESTONES: tuple[tuple[str, str, Priority, tuple[str, ...]], ...] = (
    (
        "M0",
        "Discovery",
        Priority.P0,
        ("Problem statement", "User stories", "Success metrics"),
    ),
    (
        "M1",
        "Foundation",
        Priority.P0,
        ("Repo scaffold", "Type system", "Configuration", "CI smoke test"),
    ),
    (
        "M2",
        "Core domain",
        Priority.P0,
        ("Domain model", "Persistence", "Repository contracts"),
    ),
    (
        "M3",
        "Interface layer",
        Priority.P1,
        ("API surface", "CLI surface", "Schema validation"),
    ),
    (
        "M4",
        "Cross-cutting concerns",
        Priority.P1,
        ("Logging", "Error handling", "Auth", "Observability"),
    ),
    (
        "M5",
        "Quality & release",
        Priority.P1,
        ("Tests", "Performance", "Documentation", "Packaging"),
    ),
)


def _slugify(goal: str) -> str:
    """Return a filesystem-friendly slug derived from ``goal``."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", goal.lower()).strip("-")
    return slug or "project"


def _detect_stack(goal: str) -> tuple[str, ...]:
    """Return the inferred technology stack for ``goal``."""
    lower = goal.lower()
    hints: list[str] = []
    for needle, stack in _STACK_HINTS.items():
        if re.search(rf"\b{re.escape(needle)}\b", lower):
            hints.extend(stack)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for hint in hints:
        if hint not in seen:
            seen.add(hint)
            out.append(hint)
    if not out:
        out.extend(("Python", "FastAPI", "Pydantic", "SQLite", "pytest"))
    return tuple(out)


def _classify_goal(goal: str) -> tuple[str, str]:
    """Return ``(goal_kind, project_kind)`` for ``goal``."""
    lower = goal.lower()
    for needle, label in _KEYWORD_GOALS.items():
        if re.search(rf"\b{re.escape(needle)}\b", lower):
            return label, needle
    return "an application", "app"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class PlannerOptions:
    """Toggles that influence plan generation."""

    include_tests: bool = True
    include_observability: bool = True
    max_milestones: int = 6
    extra_goals: tuple[str, ...] = field(default_factory=tuple)


def build_software_plan(goal: str, options: PlannerOptions | None = None) -> SoftwarePlan:
    """Build a :class:`SoftwarePlan` for ``goal``."""
    options = options or PlannerOptions()
    goal = goal.strip()
    if not goal:
        raise ValueError("goal must be a non-empty string")

    slug = _slugify(goal)
    label, kind = _classify_goal(goal)
    stack = _detect_stack(goal)
    summary = _build_summary(goal, label, stack)
    architecture = _build_architecture(goal, label, stack)
    folder_structure = _build_folder_structure(slug, kind, stack)
    milestones = _build_milestones(goal, kind, options)
    tasks = _build_tasks(milestones, kind, options)
    risks = _build_risks(goal, kind, stack, options)
    prompt_sequences = _build_prompt_sequences(tasks, goal, stack)

    return SoftwarePlan(
        goal=goal,
        summary=summary,
        architecture=architecture,
        folder_structure=folder_structure,
        milestones=milestones,
        tasks=tasks,
        risks=risks,
        prompt_sequences=prompt_sequences,
        notes=_build_notes(options),
    )


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_summary(goal: str, label: str, stack: Iterable[str]) -> str:
    stack_list = ", ".join(list(stack)[:4])
    return (
        f"Plan for {label}: {goal}. "
        f"Suggested stack: {stack_list}. "
        f"Each milestone is broken into tasks with explicit acceptance "
        f"criteria and a prompt sequence for an AI agent."
    )


def _build_architecture(goal: str, label: str, stack: tuple[str, ...]) -> Architecture:
    """Derive a simple three-component architecture from the goal."""
    primary = stack[0] if stack else "Python"
    components: list[Component] = [
        Component(
            name="interface",
            kind=ComponentKind.API if "api" in goal.lower() else ComponentKind.CLI,
            purpose=(
                "Public surface (HTTP API or CLI). Owns request validation, "
                "auth, and the contract exposed to callers."
            ),
            depends_on=("domain",),
        ),
        Component(
            name="domain",
            kind=ComponentKind.LIBRARY,
            purpose=(
                "Core business logic. Pure functions where possible; "
                f"implemented in {primary} with no I/O dependencies."
            ),
            depends_on=(),
        ),
        Component(
            name="persistence",
            kind=ComponentKind.DATA,
            purpose="Repository pattern over the chosen datastore.",
            depends_on=("domain",),
        ),
    ]
    flows = [
        DataFlow(source="interface", target="domain", contract="typed function calls"),
        DataFlow(source="domain", target="persistence", contract="repository interfaces"),
    ]
    return Architecture(
        summary=(
            f"Three-layer architecture for {label}, built around a pure core "
            f"with a thin interface layer and a swappable persistence layer."
        ),
        components=components,
        flows=flows,
    )


def _build_folder_structure(slug: str, kind: str, stack: tuple[str, ...]) -> FolderStructure:
    """Return the canonical project tree for the detected kind/stack."""
    children: list[FolderNode] = [
        FolderNode(path="src", purpose="Production code"),
        FolderNode(path="tests", purpose="Automated tests"),
        FolderNode(path="docs", purpose="User-facing documentation"),
        FolderNode(path="scripts", purpose="Operational scripts"),
    ]
    src = children[0]
    if kind in {"api", "service", "backend"}:
        src.children = [
            FolderNode(path="src/api", purpose="HTTP handlers + routing"),
            FolderNode(path="src/domain", purpose="Core business logic"),
            FolderNode(path="src/persistence", purpose="Datastore access"),
            FolderNode(path="src/observability", purpose="Logging, metrics, traces"),
        ]
    elif kind in {"cli"}:
        src.children = [
            FolderNode(path="src/commands", purpose="Subcommand implementations"),
            FolderNode(path="src/core", purpose="Core logic shared by commands"),
            FolderNode(path="src/output", purpose="Terminal output helpers"),
        ]
    elif kind in {"library", "sdk"}:
        src.children = [
            FolderNode(path="src", purpose="Public package surface"),
            FolderNode(path="src/_internal", purpose="Private implementation"),
        ]
    else:
        src.children = [
            FolderNode(path="src/api", purpose="HTTP handlers"),
            FolderNode(path="src/core", purpose="Core logic"),
        ]
    children.extend(
        [
            FolderNode(path=".github/workflows", purpose="CI definitions"),
            FolderNode(path="pyproject.toml", purpose="Package metadata + tooling"),
            FolderNode(path="README.md", purpose="Quickstart + overview"),
        ]
    )
    # Filter out non-pertinent top-level nodes (keep the tree tidy).
    return FolderStructure(root=slug, tree=children)


def _build_milestones(goal: str, kind: str, options: PlannerOptions) -> list[Milestone]:
    milestones: list[Milestone] = []
    for mid, title, priority, deliverables in _DEFAULT_MILESTONES[: options.max_milestones]:
        milestones.append(
            Milestone(
                id=mid,
                title=title,
                description=_milestone_description(mid, title, goal, kind),
                priority=priority,
                deliverables=list(deliverables),
            )
        )
    return milestones


def _milestone_description(mid: str, title: str, goal: str, kind: str) -> str:
    summaries: dict[str, str] = {
        "M0": f"Lock down the problem statement and success metrics for: {goal}.",
        "M1": "Set up the project skeleton, tooling, and CI smoke test.",
        "M2": f"Implement the core domain for the {kind}.",
        "M3": f"Expose the {kind}'s surface (HTTP, CLI, or library API).",
        "M4": "Wire up cross-cutting concerns: auth, logging, errors, observability.",
        "M5": "Bring the project to release quality: tests, docs, packaging.",
    }
    return summaries.get(mid, title)


def _build_tasks(
    milestones: list[Milestone], kind: str, options: PlannerOptions
) -> list[Task]:
    tasks: list[Task] = []
    counter = 0

    def _next_id() -> str:
        nonlocal counter
        counter += 1
        return f"T{counter:02d}"

    for milestone in milestones:
        per_milestone = _tasks_for_milestone(milestone, kind, options)
        for title, description, acceptance, estimate, owner in per_milestone:
            tid = _next_id()
            task = Task(
                id=tid,
                title=title,
                description=description,
                milestone_id=milestone.id,
                priority=milestone.priority,
                estimate=estimate,
                owner=owner,
                acceptance=list(acceptance),
                depends_on=[],
            )
            tasks.append(task)
            milestone.task_ids.append(tid)
    # Wire intra-milestone dependencies: each task depends on the previous.
    from itertools import pairwise

    for milestone in milestones:
        milestone_tasks = [t for t in tasks if t.milestone_id == milestone.id]
        for prev, current in pairwise(milestone_tasks):
            current.depends_on.append(prev.id)
    return tasks


def _tasks_for_milestone(
    milestone: Milestone, kind: str, options: PlannerOptions
) -> list[tuple[str, str, tuple[str, ...], str, str]]:
    if milestone.id == "M0":
        return [
            (
                "Write a one-paragraph problem statement",
                "Capture the user need and the success criteria in plain English.",
                ("Reviewed by a stakeholder", "No technical jargon"),
                "S",
                "human",
            ),
            (
                "Draft three user stories",
                "Each story follows: As a ___, I want ___, so that ___.",
                ("Three stories", "All have acceptance criteria"),
                "S",
                "human",
            ),
        ]
    if milestone.id == "M1":
        return [
            (
                "Scaffold the repository",
                "Create pyproject.toml, src/ tree, README, and a Makefile.",
                ("`pytest` runs green", "`ruff check` is clean"),
                "S",
                "agent",
            ),
            (
                "Configure CI",
                "Add a GitHub Actions workflow that runs lint + tests on PRs.",
                ("Workflow visible in .github/workflows", "PR check is green"),
                "S",
                "agent",
            ),
            (
                "Add structured logging",
                "Configure the project's logging format and level.",
                (),
                "S",
                "agent",
            ),
        ]
    if milestone.id == "M2":
        return [
            (
                "Define domain types",
                "Add Pydantic/dataclass types for the core entities.",
                ("Types are immutable", "Round-trip JSON serialization works"),
                "M",
                "agent",
            ),
            (
                "Implement domain operations",
                "Write the business rules as pure functions.",
                ("Unit tests cover edge cases", "No I/O in this layer"),
                "M",
                "agent",
            ),
            (
                "Build the persistence layer",
                "Wrap the chosen datastore behind repository interfaces.",
                ("In-memory implementation for tests", "Real implementation behind an env flag"),
                "M",
                "agent",
            ),
        ]
    if milestone.id == "M3":
        if kind in {"api", "service", "backend"}:
            return [
                (
                    "Add HTTP routing",
                    "Define routes and request/response models.",
                    ("OpenAPI schema is generated", "Validation errors are 4xx with detail"),
                    "M",
                    "agent",
                ),
                (
                    "Add error handling",
                    "Translate exceptions to typed HTTP responses.",
                    ("No 500s for known error types", "All errors logged with context"),
                    "S",
                    "agent",
                ),
            ]
        if kind == "cli":
            return [
                (
                    "Define subcommands",
                    "Use Typer/Click to declare the command surface.",
                    ("`--help` is helpful", "Subcommands have unit tests"),
                    "M",
                    "agent",
                ),
                (
                    "Add progress + error reporting",
                    "Use Rich for progress bars and styled errors.",
                    ("Errors exit non-zero", "No stack traces in default mode"),
                    "S",
                    "agent",
                ),
            ]
        return [
            (
                "Design the public API",
                "Sketch the public functions/classes and their contracts.",
                ("Docstrings on every public symbol", "At least one usage example per entry point"),
                "M",
                "agent",
            ),
            (
                "Document the public API",
                "Generate API reference docs (mkdocs/sphinx).",
                ("Docs build green", "Cross-links to guides"),
                "S",
                "agent",
            ),
        ]
    if milestone.id == "M4":
        items: list[tuple[str, str, tuple[str, ...], str, str]] = [
            (
                "Add authentication",
                "Choose an auth model and apply it at the interface boundary.",
                ("Auth failures are 401/403", "No credentials in logs"),
                "M",
                "agent",
            ),
            (
                "Add error reporting",
                "Translate exceptions to typed responses and structured logs.",
                (),
                "S",
                "agent",
            ),
        ]
        if options.include_observability:
            items.append(
                (
                    "Add metrics + tracing",
                    "Instrument key request paths with counters and spans.",
                    ("Metrics endpoint exposed", "Traces sampled at >= 1%"),
                    "M",
                    "agent",
                )
            )
        return items
    if milestone.id == "M5":
        items = [
            (
                "Write the README",
                "Document install, quickstart, and architecture overview.",
                ("Badges are green", "New contributor can follow the steps"),
                "M",
                "human",
            ),
            (
                "Add a release checklist",
                "Define pre-release steps: version bump, changelog, tag.",
                (),
                "S",
                "agent",
            ),
        ]
        if options.include_tests:
            items.append(
                (
                    "Audit test coverage",
                    "Identify gaps and add tests for the highest-risk paths.",
                    ("Coverage >= 80%", "No flaky tests on CI"),
                    "M",
                    "agent",
                )
            )
        return items
    return []


def _build_risks(
    goal: str, kind: str, stack: tuple[str, ...], options: PlannerOptions
) -> list[Risk]:
    risks: list[Risk] = [
        Risk(
            id="R1",
            description="Scope creep beyond the initial milestone set.",
            severity=RiskSeverity.MEDIUM,
            likelihood=RiskSeverity.MEDIUM,
            mitigation="Lock the M0 problem statement; require a new milestone to expand scope.",
        ),
        Risk(
            id="R2",
            description="Premature optimization of hot paths.",
            severity=RiskSeverity.LOW,
            likelihood=RiskSeverity.MEDIUM,
            mitigation="Measure first; the optimizer module already records call stats.",
        ),
        Risk(
            id="R3",
            description="External API rate limits or schema changes.",
            severity=RiskSeverity.MEDIUM,
            likelihood=RiskSeverity.MEDIUM,
            mitigation="Wrap all external calls behind interfaces; ship a mock for tests.",
        ),
    ]
    if "api" in goal.lower() or kind in {"api", "service", "backend"}:
        risks.append(
            Risk(
                id="R4",
                description="Authentication misconfiguration leaks data.",
                severity=RiskSeverity.HIGH,
                likelihood=RiskSeverity.LOW,
                mitigation="Test auth failure paths in CI; deny by default in the router.",
            )
        )
    if options.include_observability:
        risks.append(
            Risk(
                id="R5",
                description="Missing observability hides production incidents.",
                severity=RiskSeverity.MEDIUM,
                likelihood=RiskSeverity.MEDIUM,
                mitigation="Adopt structured logging + metrics before M4 ships.",
            )
        )
    return risks


def _build_prompt_sequences(
    tasks: list[Task], goal: str, stack: tuple[str, ...]
) -> list[PromptSequence]:
    stack_line = ", ".join(stack[:4]) if stack else "the chosen stack"
    out: list[PromptSequence] = []
    for task in tasks:
        system = (
            f"You are a senior engineer working on a project to {goal}. "
            f"The project uses {stack_line}. Apply the Ponytail ruleset: "
            f"ship the smallest correct change, reuse existing helpers, prefer "
            f"the standard library, and avoid speculative abstractions."
        )
        user = (
            f"Complete this task:\n\n"
            f"Title: {task.title}\n"
            f"Description: {task.description}\n"
            f"Acceptance criteria:\n"
            + "\n".join(f"- {c}" for c in task.acceptance or ["(none specified)"])
            + "\n\nReturn a unified diff, not free-form prose. "
            f"Keep the change to {task.estimate} of work."
        )
        out.append(
            PromptSequence(
                task_id=task.id,
                system=system,
                user=user,
                turns=[
                    PromptTurn(role="system", content=system),
                    PromptTurn(role="user", content=user),
                ],
            )
        )
    return out


def _build_notes(options: PlannerOptions) -> list[str]:
    notes: list[str] = []
    if options.max_milestones != 6:
        notes.append(f"max_milestones={options.max_milestones}")
    if not options.include_tests:
        notes.append("test task omitted by configuration")
    if not options.include_observability:
        notes.append("observability tasks omitted by configuration")
    if options.extra_goals:
        notes.append(f"extra goals: {', '.join(options.extra_goals)}")
    return notes


__all__ = [
    "Architecture",
    "Component",
    "ComponentKind",
    "DataFlow",
    "FolderNode",
    "FolderStructure",
    "Milestone",
    "PlannerOptions",
    "Priority",
    "PromptSequence",
    "PromptTurn",
    "Risk",
    "RiskSeverity",
    "SoftwarePlan",
    "Task",
    "TaskStatus",
    "build_software_plan",
]
