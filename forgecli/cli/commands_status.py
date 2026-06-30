"""``forgecli status`` subcommand: show the current project and tool status.

Summarizes configuration settings, active models, prompt optimizer settings,
git repository state, and index statuses in a beautiful dashboard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.align import Align
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from forgecli import __version__
from forgecli.cli.ui import get_console
from forgecli.config import ConfigLoader
from forgecli.platform import ProjectPaths, current_platform
from forgecli.sdk import PluginManager
from forgecli.utils.paths import to_privacy_path

app = typer.Typer(
    help="Show the status of the current workspace and ForgeCLI settings.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def status_cmd(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
) -> None:
    """Display status dashboard for the current project and active configuration."""
    if ctx.invoked_subcommand is not None:
        return

    console = get_console()
    target_path = Path(path).resolve()
    paths = ProjectPaths.from_env(cwd=str(target_path))

    # 1. Load active config
    config_file = target_path / "forgecli.toml"
    config_loaded = False
    config_data: dict[str, Any] = {}
    if config_file.exists():
        try:
            loader = ConfigLoader(config_file)
            settings = loader.load()
            config_data = settings.model_dump() if hasattr(settings, "model_dump") else settings.dict()
            config_loaded = True
        except Exception:
            config_loaded = False

    # 2. Get Git repo status
    git_info = _get_git_status(target_path)

    # 3. Get Graph status
    graph_json = target_path / "graphify-out" / "graph.json"
    graph_built = graph_json.exists()
    graph_size = f"{graph_json.stat().st_size / 1024:.2f} KB" if graph_built else "n/a"

    # 4. Get active plugins
    try:
        manager = PluginManager(data_root=paths.data_dir)
        plugins = manager.list()
        plugin_count = len(plugins)
    except Exception:
        plugin_count = 0

    console.print()
    # Main Header
    console.print(
        Panel(
            Align.center(
                f"[bold cyan]ForgeCLI Workspace Status[/bold cyan]\n"
                f"[dim]Project Root: {to_privacy_path(target_path)}[/dim]"
            ),
            border_style="cyan",
        )
    )
    console.print()

    # Build layout tables
    t_config = Table(title="⚙ Configuration Status", show_header=False, expand=True)
    t_config.add_column("Key", style="dim cyan")
    t_config.add_column("Value")
    t_config.add_row("Config File", "[green]Loaded[/green]" if config_loaded else "[yellow]Missing (defaults used)[/yellow]")

    app_section = config_data.get("app", {})
    t_config.add_row("Log Level", app_section.get("log_level", "INFO"))

    prov_section = config_data.get("providers", {})
    t_config.add_row("Default Provider", prov_section.get("default", "auto"))

    opt_section = config_data.get("prompt_optimizer", {})
    opt_enabled = opt_section.get("enabled", True)
    t_config.add_row(
        "Prompt Optimizer",
        f"[green]Enabled[/green] ({opt_section.get('intensity', 'lite')})" if opt_enabled else "[red]Disabled[/red]"
    )
    t_config.add_row("Optimizer Backend", opt_section.get("backend", "ruleset"))

    t_repo = Table(title="📁 Repository Status", show_header=False, expand=True)
    t_repo.add_column("Key", style="dim cyan")
    t_repo.add_column("Value")
    t_repo.add_row("Is Git Repo", "[green]✔ Yes[/green]" if git_info["is_repo"] else "[red]✘ No[/red]")
    t_repo.add_row("Active Branch", git_info["branch"])
    t_repo.add_row("HEAD Commit", git_info["head"])
    t_repo.add_row("Repo State", "[green]✔ Clean[/green]" if git_info["clean"] else "[yellow]⚠ Dirty[/yellow]")

    console.print(Columns([Panel(t_config, border_style="dim"), Panel(t_repo, border_style="dim")], equal=True))
    console.print()

    t_intel = Table(title="🤖 Code Intelligence & Extension", show_header=False, expand=True)
    t_intel.add_column("Key", style="dim cyan")
    t_intel.add_column("Value")
    t_intel.add_row("Graph Index Status", "[green]✔ Built[/green]" if graph_built else "[yellow]✘ Not Built[/yellow]")
    t_intel.add_row("Index File Size", graph_size)
    t_intel.add_row("Active Plugins", str(plugin_count))
    t_intel.add_row("Forge Version", f"v{__version__} ({current_platform().os.value})")

    console.print(Panel(t_intel, border_style="dim"))
    console.print()


def _get_git_status(path: Path) -> dict[str, Any]:
    try:
        from forgecli.git.repo import GitRepo
        repo = GitRepo(path)
        status = repo.status()
        return {
            "is_repo": True,
            "branch": status.get("branch", "unknown"),
            "clean": status.get("clean", True),
            "head": repo.head[:8] if repo.head else "unknown",
        }
    except Exception:
        return {
            "is_repo": False,
            "branch": "n/a",
            "clean": True,
            "head": "n/a",
        }


__all__ = ["app"]
