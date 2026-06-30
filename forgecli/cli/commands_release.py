"""``forge release`` subcommand: cut a release.

Combines:

* ``forge commit release <version>`` — promote the Unreleased
  changelog entries to a versioned block;
* ``git tag <version>`` — create an annotated tag;
* ``git push --follow-tags`` — push the commit and the tag.

Use ``--dry-run`` to print the actions without executing them.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import typer

from forgecli.cli.ui import error, info, success, warn
from forgecli.commit.changelog import Changelog
from forgecli.commit.release_notes import build_release_notes

app = typer.Typer(
    help="Cut a release (changelog promotion, tag, optional push).",
    invoke_without_command=True,
    rich_markup_mode="rich",
    context_settings={"allow_interspersed_args": True},
)


_SEMVER = re.compile(r"^v?\d+\.\d+\.\d+([\-+].+)?$")


@app.callback(invoke_without_command=True, context_settings={"allow_interspersed_args": True})
def release_cmd(
    ctx: typer.Context,
    version: str = typer.Argument(..., help="Version to release (e.g. 1.2.0)."),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    previous: str | None = typer.Option(
        None, "--previous", help="Previous version (for the compare link)."
    ),
    changelog_path: Path = typer.Option(
        Path("CHANGELOG.md"), "--changelog-path", help="Path to CHANGELOG.md."
    ),
    notes_path: Path | None = typer.Option(
        None, "--notes-path", help="Write release notes to this file."
    ),
    push: bool = typer.Option(
        False, "--push", help="Push the commit and the tag to the remote."
    ),
    remote: str = typer.Option("origin", "--remote", help="Remote name."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Cut a release end-to-end."""
    if ctx.invoked_subcommand is not None:
        return
    project = Path(path).resolve()
    if not _SEMVER.match(version):
        # Allow plain "1.2.0" as well as "v1.2.0".
        version = version.lstrip("v")
        if not _SEMVER.match(version):
            error(f"Version must look like 1.2.0 or v1.2.0; got {version!r}")
            raise typer.Exit(code=1)
        version = f"v{version}"

    cl = Changelog.load(changelog_path)
    if not cl.unreleased:
        warn("No Unreleased entries to release. Run 'forge commit --changelog' first.")
        raise typer.Exit(code=1)

    analyses = [entry.analysis for entry in cl.unreleased]
    notes = build_release_notes(version, analyses, previous_version=previous)
    if notes_path:
        if dry_run:
            info(f"[dry-run] would write {notes_path}")
        else:
            notes_path.parent.mkdir(parents=True, exist_ok=True)
            notes_path.write_text(notes.render(), encoding="utf-8")
            success(f"Release notes written to {notes_path}.")
    else:
        # Print to stdout.
        import sys
        sys.stdout.write(notes.render())

    if not dry_run:
        cl.release(version)
        cl.save(changelog_path)
        success(f"Changelog released as [{version}].")

    if _run_git(["add", str(changelog_path)], project, dry_run=dry_run) and not dry_run:
        success("Changelog staged.")

    if not _is_git_repo(project):
        warn("Not a git repository; skipping tag and push.")
        return

    msg = f"Release {version}"
    if _run_git(["commit", "-m", msg], project, dry_run=dry_run) and not dry_run:
        success("Release commit created.")
    _run_git(["tag", "-a", version, "-m", msg], project, dry_run=dry_run)
    if dry_run:
        info(f"[dry-run] would create tag {version}")
    else:
        success(f"Tag {version} created.")

    if push:
        _run_git(["push", remote], project, dry_run=dry_run)
        _run_git(["push", remote, version], project, dry_run=dry_run)
        if not dry_run:
            success(f"Pushed commit and tag to {remote}.")


def _run_git(args: list[str], project: Path, *, dry_run: bool) -> bool:
    if dry_run:
        info(f"[dry-run] git {' '.join(args)}")
        return True
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(project),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        error(f"git not found: {exc}")
        raise typer.Exit(code=1) from exc
    if result.returncode != 0:
        error(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        raise typer.Exit(code=1)
    return True


def _is_git_repo(project: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(project),
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


__all__ = ["app"]
