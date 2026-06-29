"""``forgecli review`` subcommand."""

from __future__ import annotations

import typer

from forgecli.cli.ui import success

app = typer.Typer(help="Review code changes.", no_args_is_help=True)


@app.command("run")
def run() -> None:
    """Run a placeholder review pass."""
    success("Review complete (placeholder, no findings).")


__all__ = ["app"]
