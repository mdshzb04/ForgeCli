"""Rich + JSON + Markdown renderers for a :class:`RepositoryReview`."""

from __future__ import annotations

import json
from collections.abc import Iterable

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from forgecli.review.finding import Finding, Severity
from forgecli.review.repository import RepositoryReview
from forgecli.review.suggestions import Suggestion

_SEVERITY_STYLE: dict[Severity, str] = {
    Severity.INFO: "cyan",
    Severity.LOW: "green",
    Severity.MEDIUM: "yellow",
    Severity.HIGH: "bold red",
    Severity.CRITICAL: "bold magenta on red",
}


def print_review(review: RepositoryReview, console: Console | None = None) -> None:
    """Print a :class:`RepositoryReview` using the given Rich console."""
    console = console or Console()
    for renderable in render_review(review):
        console.print(renderable)


def render_review(review: RepositoryReview) -> list:
    """Return a list of Rich renderables that visualize ``review``."""
    out: list = []
    out.append(_render_header(review))
    out.append(_render_summary(review))
    if review.suggestions:
        out.append(_render_suggestions(review.suggestions))
    if review.findings:
        out.append(_render_findings(review.findings))
    if not review.findings:
        out.append(Panel("[green]No findings.[/green]", border_style="green"))
    return out


# ---------------------------------------------------------------------------
# JSON / Markdown
# ---------------------------------------------------------------------------


def review_to_json(review: RepositoryReview, *, indent: int = 2) -> str:
    """Return the review as a JSON string."""
    return json.dumps(review.to_dict(), indent=indent)


def review_to_markdown(review: RepositoryReview) -> str:
    """Return a Markdown rendering of ``review``."""
    parts: list[str] = []
    parts.append(f"# Review: {review.root}\n")
    counts = review.counts_by_severity()
    parts.append("## Summary")
    parts.append("")
    parts.append(f"- Files analyzed: {review.stats.get('files', 0)}")
    parts.append(f"- Analyzers run: {', '.join(review.analyzer_names)}")
    parts.append(
        f"- Findings: {len(review.findings)} "
        f"(critical={counts[Severity.CRITICAL]}, "
        f"high={counts[Severity.HIGH]}, "
        f"medium={counts[Severity.MEDIUM]}, "
        f"low={counts[Severity.LOW]}, "
        f"info={counts[Severity.INFO]})"
    )
    if review.suggestions:
        parts.append("## Suggestions")
        parts.append("")
        for suggestion in review.suggestions:
            parts.append(
                f"- **[{suggestion.severity.value}] {suggestion.title}** "
                f"({suggestion.count} occurrence{'s' if suggestion.count != 1 else ''})"
            )
            if suggestion.rationale:
                parts.append(f"    - {suggestion.rationale}")
    if review.findings:
        parts.append("## Findings")
        parts.append("")
        parts.append("| Severity | Category | Rule | Path | Line | Message |")
        parts.append("| --- | --- | --- | --- | --- | --- |")
        for finding in review.findings:
            parts.append(
                "| {sev} | {cat} | {rule} | {path} | {line} | {msg} |".format(
                    sev=finding.severity.value,
                    cat=finding.category,
                    rule=finding.rule_id,
                    path=_shorten_path(finding.path) if finding.path else "",
                    line=finding.line or "",
                    msg=_escape(finding.message),
                )
            )
    if not review.findings:
        parts.append("\n_No findings._")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Rich sections
# ---------------------------------------------------------------------------


def _render_header(review: RepositoryReview) -> Panel:
    counts = review.counts_by_severity()
    critical = counts[Severity.CRITICAL]
    high = counts[Severity.HIGH]
    title_text = f"[bold]Code review:[/bold] {review.root}"
    if critical:
        title_text += f"  [critical on red] {critical} critical [/]"
    if high:
        title_text += f"  [red] {high} high [/]"
    return Panel(
        title_text,
        border_style="magenta",
        title="forge review",
    )


def _render_summary(review: RepositoryReview) -> Panel:
    counts = review.counts_by_severity()
    by_category = review.counts_by_category()
    table = Table(
        title="Counts",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    table.add_column("Severity")
    table.add_column("Count", justify="right")
    for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
        count = counts.get(severity, 0)
        table.add_row(
            TextRenderable(severity.value, style=_SEVERITY_STYLE[severity]),
            str(count),
        )
    cat = Table(
        title="By category",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    cat.add_column("Category")
    cat.add_column("Count", justify="right")
    for name, count in sorted(by_category.items()):
        cat.add_row(name, str(count))
    stats = Table(
        title="Stats",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    stats.add_column("Field")
    stats.add_column("Value")
    for key, value in review.stats.items():
        stats.add_row(key, str(value))
    return Panel(
        Group(table, TextRenderable(""), cat, TextRenderable(""), stats),
        title="Summary",
        border_style="cyan",
    )


def _render_suggestions(suggestions: Iterable[Suggestion]) -> Panel:
    table = Table(
        title="Suggested actions",
        title_style="bold cyan",
        header_style="bold magenta",
        show_lines=False,
        expand=True,
    )
    table.add_column("Severity", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Action")
    table.add_column("Count", justify="right")
    for suggestion in suggestions:
        table.add_row(
            TextRenderable(
                suggestion.severity.value, style=_SEVERITY_STYLE[suggestion.severity]
            ),
            suggestion.category,
            suggestion.title,
            str(suggestion.count),
        )
    return Panel(table, title="Suggestions", border_style="cyan")


def _render_findings(findings: Iterable[Finding]) -> Panel:
    by_category: dict[str, list[Finding]] = {}
    for finding in findings:
        by_category.setdefault(finding.category, []).append(finding)

    panels: list = []
    for category in sorted(by_category):
        rows = by_category[category]
        table = Table(
            title=f"{category} ({len(rows)})",
            title_style="bold cyan",
            header_style="bold magenta",
            show_lines=True,
            expand=True,
        )
        table.add_column("Sev", no_wrap=True)
        table.add_column("Rule", no_wrap=True)
        table.add_column("Path:Line", no_wrap=True)
        table.add_column("Message", overflow="fold")
        table.add_column("Suggestion", overflow="fold", style="muted")
        for finding in rows:
            location = (
                f"{_shorten_path(finding.path)}:{finding.line}"
                if finding.path and finding.line
                else finding.path or ""
            )
            table.add_row(
                TextRenderable(
                    finding.severity.value, style=_SEVERITY_STYLE[finding.severity]
                ),
                finding.rule_id,
                location,
                finding.message,
                finding.suggestion or "",
            )
        panels.append(table)
    return Panel(Group(*panels), title="Findings", border_style="cyan")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TextRenderable:
    """A small wrapper around :class:`rich.text.Text` that gives us a
    :meth:`copy` method (Rich's Panel calls ``self.title.copy()`` on
    non-string titles) without forcing every call site to import
    ``rich.text``.
    """

    def __init__(self, text: str, style: str | None = None) -> None:
        from rich.text import Text

        self._text = Text(text, style=style)

    def __rich_console__(self, console: Console, options):
        yield from console.render(self._text, options)

    def copy(self) -> TextRenderable:
        return TextRenderable.__new__(TextRenderable)._copy_from(self)

    def _copy_from(self, other: TextRenderable) -> TextRenderable:
        self._text = other._text.copy()
        return self

    def __str__(self) -> str:
        return str(self._text)


def _shorten_path(path: str | None) -> str:
    if path is None:
        return ""
    parts = path.split("/")
    if len(parts) > 4:
        return "/".join(parts[-3:])
    return path


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "print_review",
    "render_review",
    "review_to_json",
    "review_to_markdown",
]
