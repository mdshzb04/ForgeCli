"""``forge explain`` top-level command (alias for ``forge graph explain``)."""

from __future__ import annotations

import typer

from forgecli.cli import commands_graph
from forgecli.cli.ui import error

app = typer.Typer(
    help="Explain a node, file, or symbol using the Graphify knowledge graph.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Node label, id, or filename to explain."),
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
) -> None:
    """Forward to ``forge graph explain``."""

    try:
        commands_graph.explain_cmd(target=target, path=path)
    except typer.Exit as exc:
        raise exc
    except Exception as exc:
        error(f"Explain failed: {exc}")
        raise typer.Exit(code=1) from exc
    _ = ctx  # silence unused


__all__ = ["app"]
