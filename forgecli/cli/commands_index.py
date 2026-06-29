"""``forgecli index`` subcommand."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, success
from forgecli.graph.indexer import Indexer

app = typer.Typer(help="Build the repository code graph.", no_args_is_help=True)


@app.command("run")
def run(
    path: str = typer.Option(".", "--path", "-p", help="Project root to index."),
) -> None:
    """Index ``path`` into the in-memory code graph (placeholder)."""
    context = bootstrap_context()
    indexer: Indexer = context.container.resolve(Indexer)
    summary = indexer.index()
    get_console().print(summary)
    success("Indexing complete (placeholder).")


__all__ = ["app"]
