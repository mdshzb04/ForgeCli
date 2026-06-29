"""``forgecli init`` subcommand."""

from __future__ import annotations

import typer
from rich.panel import Panel

from forgecli import __version__
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, success

app = typer.Typer(help="Initialize a ForgeCLI project.", no_args_is_help=True)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root to initialize."),
) -> None:
    """Print a banner and write a starter ``forgecli.toml`` (placeholder)."""
    if ctx.invoked_subcommand is not None:
        return

    context = bootstrap_context(cwd=None)
    console = get_console()
    console.print(
        Panel(
            f"[accent]ForgeCLI[/accent] v{__version__}\n"
            f"Working directory: [muted]{context.cwd}[/muted]",
            title="forgecli init",
            border_style="magenta",
        )
    )
    success("Project initialized (placeholder).")


__all__ = ["app"]
