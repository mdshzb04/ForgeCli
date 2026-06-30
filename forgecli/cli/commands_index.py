"""``forgecli index`` subcommand."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, success
from forgecli.graph.indexer import Indexer

app = typer.Typer(
    help="Build the repository code graph.",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context) -> None:
    """Build the repository code graph."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(run, path=".")


@app.command("run")
def run(
    path: str = typer.Option(".", "--path", "-p", help="Project root to index."),
) -> None:
    """Index ``path`` into the in-memory code graph."""
    context = bootstrap_context()
    indexer: Indexer = context.container.resolve(Indexer)
    summary = indexer.index()
    get_console().print(summary)
    success("Indexing complete.")


__all__ = ["app"]
