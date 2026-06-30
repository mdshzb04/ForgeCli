"""``forgecli info`` subcommand: show platform environment and app details.

Prints installation paths, binary paths, system specifications, default directories,
and information about supported provider entry points.
"""

from __future__ import annotations

import sys

import typer
from rich import box
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from forgecli import __app_name__, __version__
from forgecli.cli.ui import get_console
from forgecli.platform import ProjectPaths, current_platform, python_version

app = typer.Typer(
    help="Display info about the system, directories, and ForgeCLI installation.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def info_cmd(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
) -> None:
    """Display information details about the ForgeCLI application and system environment."""
    if ctx.invoked_subcommand is not None:
        return

    console = get_console()
    platform = current_platform()
    paths = ProjectPaths.from_env(cwd=path)

    console.print()
    console.print(
        Panel(
            Align.center(
                "[bold cyan]ForgeCLI Information[/bold cyan]\n"
                "[dim]The AI-first developer operating system[/dim]"
            ),
            border_style="cyan",
        )
    )
    console.print()

    # Create tables
    t_system = Table(title="💻 System Information", show_header=False, expand=True, box=box.SIMPLE)
    t_system.add_column("Key", style="dim cyan")
    t_system.add_column("Value")
    t_system.add_row("OS Platform", platform.os.value)
    t_system.add_row("Architecture", platform.arch)
    t_system.add_row("OS Release", platform.release or "unknown")
    t_system.add_row("Python Version", python_version())
    t_system.add_row("Python Executable", sys.executable)
    t_system.add_row("WSL", "Yes" if platform.is_wsl else "No")

    from forgecli.utils.paths import to_privacy_path

    t_app = Table(title="⚙ Application details", show_header=False, expand=True, box=box.SIMPLE)
    t_app.add_column("Key", style="dim cyan")
    t_app.add_column("Value")
    t_app.add_row("App Name", __app_name__)
    t_app.add_row("App Version", __version__)
    t_app.add_row("Config Directory", to_privacy_path(paths.config_dir))
    t_app.add_row("Data Directory", to_privacy_path(paths.data_dir))
    t_app.add_row("Cache Directory", to_privacy_path(paths.cache_dir))
    t_app.add_row("Logs Directory", to_privacy_path(paths.logs_dir))
    t_app.add_row("Plugins Directory", to_privacy_path(paths.plugins_dir))

    console.print(Panel(t_system, border_style="dim"))
    console.print()
    console.print(Panel(t_app, border_style="dim"))
    console.print()


__all__ = ["app"]
