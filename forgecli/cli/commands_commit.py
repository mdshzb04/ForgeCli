"""``forge commit`` subcommand.

The headline flow:

  1. read the current git diff (staged by default, or the working tree);
  2. analyze it via :class:`CommitAnalyzer` to infer kind/scope/summary;
  3. show the proposed message;
  4. (with ``--yes``) stage all and create the commit;
  5. (with ``--changelog``) append the entry to CHANGELOG.md;
  6. (with ``--push``) push the commit to ``origin``.

Use ``--dry-run`` to inspect the message + changelog draft without
touching anything.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
from pathlib import Path

import typer

from forgecli.cli.ui import error, get_console, info, success, table, warn
from forgecli.commit.analyzer import CommitAnalyzer, CommitKind
from forgecli.commit.changelog import Changelog
from forgecli.commit.git_utils import (
    GitRepoError,
    current_branch,
    diff_staged,
    diff_unstaged,
    has_staged_changes,
    is_git_repo,
    push,
    status_porcelain,
)
from forgecli.commit.message import build_message, build_subject
from forgecli.commit.release_notes import build_release_notes

app = typer.Typer(
    help="Analyze the git diff, generate a semantic commit message, "
         "update the changelog, optionally push.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


_DEFAULT_CHANGELOG = Path("CHANGELOG.md")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def commit_cmd(
    ctx: typer.Context,
    message: str | None = typer.Option(
        None, "-m", "--message", help="Override the generated message."
    ),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    all_files: bool = typer.Option(
        False, "--all", "-a", help="Stage every modified file before committing."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Apply the commit without confirmation."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen; make no changes."
    ),
    changelog: bool = typer.Option(
        False, "--changelog", help="Append the entry to CHANGELOG.md."
    ),
    changelog_path: Path = typer.Option(
        _DEFAULT_CHANGELOG, "--changelog-path", help="Path to CHANGELOG.md."
    ),
    release_notes: bool = typer.Option(
        False, "--release-notes", help="Render release notes to stdout."
    ),
    push_remote: str | None = typer.Option(
        None, "--push", help="Push to this remote (e.g. 'origin')."
    ),
    signoff: bool = typer.Option(
        False, "--signoff", help="Add a Signed-off-by trailer."
    ),
) -> None:
    """Generate a semantic commit message and create the commit."""
    if ctx.invoked_subcommand is not None:
        return

    project = Path(path).resolve()
    if not is_git_repo(project):
        error(f"{project} is not inside a git working tree.")
        raise typer.Exit(code=1)

    if all_files and not dry_run:
        try:
            _run_git(["add", "-A"], project)
        except GitRepoError as exc:
            error(f"git add failed: {exc}")
            raise typer.Exit(code=1) from exc

    diff = diff_staged(project) or diff_unstaged(project)
    if not diff.strip():
        warn(
            "No changes to commit. Stage files (git add ...) or use --all."
        )
        raise typer.Exit(code=1)

    analyzer = CommitAnalyzer()
    analysis = analyzer.analyze(diff)
    final_message = message or build_message(analysis)
    if message:
        # When the user provides a message, we still record their choice
        # in the analysis summary so the changelog bullet is informative.
        analysis.summary = message.splitlines()[0]

    _print_plan(analysis, final_message, project)

    if release_notes:
        notes = build_release_notes("0.0.0", [analysis])
        get_console().print()
        get_console().print(notes.render())

    if dry_run:
        info("Dry run; no changes were made.")
        return

    if not yes:
        prompt = "Commit with this message? [y/N/edit] "
        try:
            answer = input(prompt).strip().lower()
        except EOFError:  # pragma: no cover - non-interactive shell
            answer = "n"
        if answer == "edit":
            edited = _open_editor_for_message(final_message, project)
            if edited is None:
                warn("Editor exited without changes; aborting.")
                raise typer.Exit(code=1)
            final_message = edited
        elif answer not in ("y", "yes"):
            warn("Aborted.")
            raise typer.Exit(code=1)

    if not has_staged_changes(project):
        try:
            _run_git(["add", "-A"], project)
        except GitRepoError as exc:
            error(f"git add failed: {exc}")
            raise typer.Exit(code=1) from exc

    sha = _git_commit(final_message, project, signoff=signoff)
    if sha:
        success(f"Committed {sha[:8]}: {build_subject(analysis)}")

    if changelog:
        cl = Changelog.load(changelog_path)
        cl.add(analysis)
        if dry_run:
            info("Dry run; changelog not written.")
        else:
            cl.save(changelog_path)
            success(f"Changelog updated: {changelog_path}")

    if push_remote:
        try:
            output = push(project, remote=push_remote)
            success(f"Pushed to {push_remote}/{current_branch(project)}.")
            if output.strip():
                get_console().print(output.strip())
        except GitRepoError as exc:
            error(str(exc))
            raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# Subcommand: `forge commit release <version>`
# ---------------------------------------------------------------------------


@app.command("release")
def release_cmd(
    version: str = typer.Argument(..., help="Version to release (e.g. 1.2.0)."),
    previous: str | None = typer.Option(
        None, "--previous", help="Previous version (for the compare link)."
    ),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    changelog_path: Path = typer.Option(
        _DEFAULT_CHANGELOG, "--changelog-path", help="Path to CHANGELOG.md."
    ),
    notes_path: Path | None = typer.Option(
        None, "--notes-path", help="Write the release notes to this file."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Render but do not write."
    ),
) -> None:
    """Render release notes from the current Unreleased changelog entries."""
    cl = Changelog.load(changelog_path)
    if not cl.unreleased:
        warn("No Unreleased entries to release. Use 'forge commit --changelog' first.")
        raise typer.Exit(code=1)

    analyses = [entry.analysis for entry in cl.unreleased]
    notes = build_release_notes(version, analyses, previous_version=previous)
    rendered = notes.render()
    if notes_path:
        if dry_run:
            info("Dry run; release notes not written.")
        else:
            notes_path.parent.mkdir(parents=True, exist_ok=True)
            notes_path.write_text(rendered, encoding="utf-8")
            success(f"Release notes written to {notes_path}.")
    else:
        get_console().print(rendered)

    if not dry_run:
        released = cl.release(version)
        cl.save(changelog_path)
        success(
            f"Changelog released as [{released.version}] - {released.date}."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_plan(analysis, final_message: str, project: Path) -> None:
    console = get_console()
    console.print()
    console.print("[bold]Proposed commit message:[/bold]")
    console.print("```")
    console.print(final_message.rstrip())
    console.print("```")
    console.print()
    rows: list[list[str]] = [
        ["Kind", analysis.kind.value],
        ["Scope", analysis.scope or "(mixed)"],
        ["Files", str(analysis.total_files)],
        ["+", str(analysis.stats.get("insertions", 0))],
        ["-", str(analysis.stats.get("deletions", 0))],
        ["Breaking", "yes" if analysis.breaking else "no"],
        ["Branch", current_branch(project)],
    ]
    table(["Field", "Value"], rows, title="Analysis")
    console.print()
    console.print("[muted]Rationale:[/muted]")
    for reason in analysis.rationale:
        console.print(f"  • {reason}")


def _open_editor_for_message(initial: str, project: Path) -> str | None:
    """Open ``$EDITOR`` (or ``vi``) with ``initial`` content; return edited text."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(initial)
        path = Path(handle.name)
    try:
        result = subprocess.run(
            [editor, str(path)],
            cwd=str(project),
            check=False,
        )
        if result.returncode != 0:
            warn(f"editor exited with code {result.returncode}")
        content = path.read_text(encoding="utf-8")
    finally:
        with contextlib.suppress(OSError):
            path.unlink()
    # Strip the conventional comment line "# " that the editor prepends.
    lines = [line for line in content.splitlines() if not line.startswith("# ")]
    edited = "\n".join(lines).strip()
    return edited or None


def _run_git(args: list[str], project: Path) -> str:
    """Run a git command and return stdout, raising on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(project),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitRepoError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or 'unknown error'}"
        )
    return result.stdout


def _git_commit(message: str, project: Path, *, signoff: bool) -> str:
    """Create a commit with ``message`` and return the resulting SHA."""
    args = ["commit", "-m", message]
    if signoff:
        args.append("--signoff")
    try:
        output = _run_git(args, project)
    except GitRepoError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc
    # ``git commit`` writes the new SHA to stdout; parse it.
    for line in output.splitlines():
        line = line.strip()
        if line and all(c in "0123456789abcdef" for c in line):
            return line
    # Fallback: ask git for HEAD.
    try:
        return _run_git(["rev-parse", "HEAD"], project).strip()
    except GitRepoError:
        return ""


__all__ = ["app"]


# Silence unused-import warnings.
