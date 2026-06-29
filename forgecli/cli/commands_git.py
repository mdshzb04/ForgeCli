"""``forgecli git`` subcommand group."""

from __future__ import annotations

import typer

from forgecli.cli.ui import success
from forgecli.core.errors import GitError

app = typer.Typer(help="Inspect and operate on the git repository.", no_args_is_help=True)


@app.command("status")
def status() -> None:
    """Show repository status (placeholder)."""
    try:
        from pathlib import Path

        from forgecli.git.repo import GitRepo

        repo = GitRepo(Path.cwd())
    except GitError as exc:
        raise typer.Exit(code=1) from exc
    success(f"Branch: {repo.status().get('branch', 'unknown')}")


@app.command("commit")
def commit(
    message: str = typer.Option(..., "-m", "--message", help="Commit message."),
) -> None:
    """Create a commit (placeholder)."""
    success("Commit not created (placeholder).")


__all__ = ["app"]
