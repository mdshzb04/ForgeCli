"""``forgecli update`` subcommand: check for newer versions of ForgeCLI.

Hits PyPI to find if a newer release is published, showing a beautiful
spinner and progress logs.
"""

from __future__ import annotations

import typer
from rich.align import Align
from rich.panel import Panel

from forgecli import __version__
from forgecli.cli.ui import get_console, success, warn
from forgecli.platform import check_for_update, upgrade_command

app = typer.Typer(
    help="Check for updates and display upgrade instructions.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def update_cmd(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache from PyPI."),
) -> None:
    """Check PyPI for a newer release and display a premium upgrade banner."""
    if ctx.invoked_subcommand is not None:
        return

    console = get_console()
    console.print()

    with console.status("[bold cyan]Checking PyPI registry for updates...[/bold cyan]", spinner="dots"):
        try:
            info = check_for_update(force=force)
        except Exception as exc:
            if "404" in str(exc):
                warn("Could not contact update registry: ForgeCLI is not published to PyPI yet (development installation).")
            else:
                warn(f"Could not contact update registry: {exc}")
            raise typer.Exit(code=0) from None

    if info.error and info.latest is None:
        if "404" in info.error:
            warn("Could not contact update registry: ForgeCLI is not published to PyPI yet (development installation).")
        else:
            warn(f"Could not contact update registry: {info.error}")
        raise typer.Exit(code=0) from None

    if info.update_available:
        console.print(
            Panel(
                Align.center(
                    f"🚀  [bold green]Update Available![/bold green]\n\n"
                    f"Current Version: [yellow]v{info.current}[/yellow]\n"
                    f"Latest Version:  [green]v{info.latest}[/green]\n\n"
                    f"Upgrade now using:\n"
                    f"[bold cyan]{upgrade_command()}[/bold cyan]"
                ),
                border_style="green",
                padding=(1, 2),
            )
        )
    else:
        success(f"You are on the latest version of ForgeCLI (v{__version__}).")
        console.print()


__all__ = ["app"]
