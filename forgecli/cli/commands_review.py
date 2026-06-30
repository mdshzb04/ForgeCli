"""``forgecli review`` subcommand: analyze a repository end-to-end.

Runs the full analyzer stack and produces a Rich, JSON, or Markdown
report. Use ``--only`` to restrict to specific categories, and
``--severity`` to filter the output. Exit code is 1 when any
critical finding is present.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from forgecli.cli.ui import error, get_console, success, table, warn
from forgecli.review import (
    RepositoryReview,
    Severity,
    print_review,
    review_repository,
    review_to_json,
    review_to_markdown,
)
from forgecli.utils.paths import to_privacy_path

app = typer.Typer(
    help="Run a code-quality review (security, performance, architecture, "
         "complexity, dead code, duplicates).",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


_ALLOWED_CATEGORIES = (
    "security",
    "performance",
    "architecture",
    "complexity",
    "dead-code",
    "duplicates",
)


@app.callback(invoke_without_command=True)
def review_cmd(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root to analyze."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    md_output: bool = typer.Option(False, "--md", help="Emit Markdown."),
    save: Path | None = typer.Option(
        None, "--save", help="Save the report to a file (--md or --json to choose the format)."
    ),
    severity: str | None = typer.Option(
        None,
        "--severity",
        help="Minimum severity to report (info|low|medium|high|critical).",
    ),
    only: str | None = typer.Option(
        None,
        "--only",
        help="Comma-separated list of categories to include.",
    ),
    exclude: str | None = typer.Option(
        None,
        "--exclude",
        help="Comma-separated list of categories to skip.",
    ),
    fail_on_critical: bool = typer.Option(
        False,
        "--fail-on-critical",
        help="Exit with code 1 if any critical finding is present.",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Display all findings without capping at Top 10.",
    ),
) -> None:
    """Run the full repository review and print a report."""
    if ctx.invoked_subcommand is not None:
        return

    review: RepositoryReview = review_repository(Path(path).resolve())
    review = _filter(review, severity=severity, only=only, exclude=exclude)

    if save is not None:
        if md_output or save.suffix == ".md":
            target = save if save.suffix == ".md" else save.with_suffix(".md")
            target.write_text(review_to_markdown(review), encoding="utf-8")
            success(f"Markdown report written to {to_privacy_path(target)}.")
        else:
            target = save if save.suffix == ".json" else save.with_suffix(".json")
            target.write_text(review_to_json(review), encoding="utf-8")
            success(f"JSON report written to {to_privacy_path(target)}.")

    if json_output:
        sys.stdout.write(review_to_json(review))
        sys.stdout.write("\n")
        sys.stdout.flush()
    elif md_output:
        sys.stdout.write(review_to_markdown(review))
        sys.stdout.flush()
    else:
        print_review(review, console=get_console(), full=full)

    _print_summary(review)
    if fail_on_critical and review.is_blocking:
        raise typer.Exit(code=1)


@app.command("categories")
def categories_cmd() -> None:
    """List the categories the review covers."""
    rows: list[list[str]] = []
    descriptions = {
        "security": "Hard-coded secrets, unsafe calls, weak hashes, asserts.",
        "performance": "Blocking I/O in async code, deeply nested loops.",
        "architecture": "Layer dependency direction, circular imports, forbidden imports.",
        "complexity": "Function length, parameter count, cyclomatic complexity.",
        "dead-code": "Private symbols that are never referenced.",
        "duplicates": "Near-duplicate code blocks across files.",
    }
    for category in _ALLOWED_CATEGORIES:
        rows.append([category, descriptions[category]])
    table(["Category", "Description"], rows, title="Review categories")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter(
    review: RepositoryReview,
    *,
    severity: str | None,
    only: str | None,
    exclude: str | None,
) -> RepositoryReview:
    """Return a copy of ``review`` filtered by severity / category."""
    min_sev: Severity | None = None
    if severity is not None:
        try:
            min_sev = Severity(severity.lower())
        except ValueError:
            error(f"Unknown severity: {severity}")
            raise typer.Exit(code=2) from None
    only_set = {name.strip() for name in (only or "").split(",") if name.strip()}
    exclude_set = {name.strip() for name in (exclude or "").split(",") if name.strip()}
    if only_set and not only_set.issubset(set(_ALLOWED_CATEGORIES)):
        error(f"Unknown categories in --only: {sorted(only_set - set(_ALLOWED_CATEGORIES))}")
        raise typer.Exit(code=2)
    if exclude_set and not exclude_set.issubset(set(_ALLOWED_CATEGORIES)):
        error(f"Unknown categories in --exclude: {sorted(exclude_set - set(_ALLOWED_CATEGORIES))}")
        raise typer.Exit(code=2)

    def keep(finding) -> bool:
        if min_sev is not None and finding.severity.weight < min_sev.weight:
            return False
        if only_set and finding.category not in only_set:
            return False
        return not exclude_set or finding.category not in exclude_set

    findings = [f for f in review.findings if keep(f)]
    suggestions = [s for s in review.suggestions if s.category not in exclude_set and (not only_set or s.category in only_set)]
    # Re-filter suggestions to those whose findings survived.
    kept_ids = {id(f) for f in findings}
    suggestions = [
        type(suggestions[0])(
            title=s.title,
            severity=s.severity,
            category=s.category,
            findings=[f for f in s.findings if id(f) in kept_ids],
            rationale=s.rationale,
        )
        for s in suggestions
        if any(id(f) in kept_ids for f in s.findings)
    ]
    return RepositoryReview(
        root=review.root,
        findings=findings,
        suggestions=suggestions,
        analyzer_names=review.analyzer_names,
        stats=review.stats,
    )


def _print_summary(review: RepositoryReview) -> None:
    counts = review.counts_by_severity()
    rows = [
        ["Files", str(review.stats.get("files", 0))],
        ["Findings", str(len(review.findings))],
        ["Suggestions", str(len(review.suggestions))],
        ["Critical", str(counts[Severity.CRITICAL])],
        ["High", str(counts[Severity.HIGH])],
        ["Medium", str(counts[Severity.MEDIUM])],
        ["Low", str(counts[Severity.LOW])],
        ["Info", str(counts[Severity.INFO])],
    ]
    table(["Field", "Value"], rows, title="Summary")
    if review.is_blocking:
        warn("Critical findings present; rerun with --fix (not yet implemented).")
    else:
        success("No critical findings.")


__all__ = ["app"]


# Silence unused-import warnings for symbols only used in some branches.
_ = json
