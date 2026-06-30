"""``forgecli doctor`` subcommand: run a self-check.

Diagnoses the current host (OS, dependencies, config, git, graph index, API keys)
and prints a premium, dashboard-style Rich report with a calculated health score.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from rich.align import Align
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table

from forgecli import __version__
from forgecli.cli.ui import error, get_console
from forgecli.platform import (
    ProjectPaths,
    check_dependencies,
    current_platform,
    install_hint,
    load_dotenv,
    python_version,
)
from forgecli.platform.deps import DependencyStatus
from forgecli.sdk import PluginManager
from forgecli.utils.paths import to_privacy_path

app = typer.Typer(
    help="Diagnose the current host (OS, dependencies, configuration, keys).",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def doctor_cmd(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero if any required dependency is missing.",
    ),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
) -> None:
    """Print a self-check report and exit with the appropriate code."""
    if ctx.invoked_subcommand is not None:
        return
    # Load a local .env if present (does not override the env).
    load_dotenv(path=Path(path) / ".env", override=False)

    platform = current_platform()
    paths = ProjectPaths.from_env(cwd=path)
    report = check_dependencies()

    # ── 1. API Keys detection ─────────────────────────────────────────
    api_status = _get_api_keys_status()

    # ── 2. Git Status detection ───────────────────────────────────────
    git_info = _get_git_status(path)

    # ── 3. Graph status ───────────────────────────────────────────────
    graph_info = _get_graph_status(path, report)

    # ── 4. Plugin Status detection ────────────────────────────────────
    plugin_info = _get_plugin_status(paths)

    # ── 5. Health Score Calculation ───────────────────────────────────
    health_score, breakdown, reasons, deductions = _calculate_health_score(report, api_status, git_info, graph_info)

    if json_output:
        payload = {
            "forge_version": __version__,
            "platform": platform.os.value,
            "arch": platform.arch,
            "python": python_version(),
            "is_wsl": platform.is_wsl,
            "config_dir": to_privacy_path(paths.config_dir),
            "data_dir": to_privacy_path(paths.data_dir),
            "health_score": health_score,
            "health_score_breakdown": breakdown,
            "api_keys": api_status,
            "git": git_info,
            "graph": graph_info,
            "plugins": plugin_info,
            "dependencies": report.to_dict(),
        }
        sys.stdout.write(json.dumps(payload, indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        _render_dashboard(
            platform, paths, report, api_status, git_info, graph_info, plugin_info, health_score, breakdown, reasons, deductions
        )

    if strict and report.missing_required:
        missing = ", ".join(d.name for d in report.missing_required)
        error(f"Required dependencies are missing: {missing}")
        raise typer.Exit(code=1)

    if report.missing_required:
        raise typer.Exit(code=1)


def _get_api_keys_status() -> dict[str, bool]:
    keys = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GOOGLE_API_KEY": "google",
        "GEMINI_API_KEY": "google",
        "GROQ_API_KEY": "groq",
        "MISTRAL_API_KEY": "mistral",
        "OPENROUTER_API_KEY": "openrouter",
    }
    return {env_var: os.environ.get(env_var) is not None for env_var in keys}


def _get_git_status(path: str) -> dict[str, Any]:
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


def _get_graph_status(path: str, report: Any) -> dict[str, Any]:
    graphify_installed = any(d.name == "graphify" and d.status == DependencyStatus.FOUND for d in report.dependencies)
    graph_json = Path(path) / "graphify-out" / "graph.json"
    index_exists = graph_json.exists()
    index_size = graph_json.stat().st_size if index_exists else 0
    return {
        "graphify_installed": graphify_installed,
        "index_built": index_exists,
        "index_size_bytes": index_size,
    }


def _get_plugin_status(paths: ProjectPaths) -> dict[str, Any]:
    try:
        manager = PluginManager(data_root=paths.data_dir)
        plugins = manager.list()
        return {
            "count": len(plugins),
            "plugins": [s.name for s, _ in plugins],
            "enabled_count": sum(1 for s, _ in plugins if s.enabled),
        }
    except Exception:
        return {
            "count": 0,
            "plugins": [],
            "enabled_count": 0,
        }


def _calculate_health_score(
    report: Any, api_status: dict[str, bool], git_info: dict[str, Any], graph_info: dict[str, Any]
) -> tuple[int, dict[str, int], list[str], list[str]]:
    reasons = []
    deductions = []

    # 1. Configuration (20 points max)
    config_score = 0
    config_exists = Path("forgecli.toml").exists()
    env_exists = Path(".env").exists()
    if config_exists:
        config_score += 10
    else:
        reasons.append("Missing configuration file `forgecli.toml` (Run `forge init`)")
    if env_exists:
        config_score += 10
    else:
        reasons.append("Missing `.env` file (Run `forge init` to generate one)")

    if config_score < 20:
        deduct_pts = 20 - config_score
        parts = []
        if not config_exists:
            parts.append("missing forgecli.toml")
        if not env_exists:
            parts.append("missing .env")
        deductions.append(
            f"[bold red]Configuration[/bold red] (-{deduct_pts} pts): due to {', '.join(parts)}.\n"
            f"  [cyan]↳ Next Step:[/cyan] Run [bold]forge init[/bold] to generate configuration and environment files."
        )

    # 2. Git (20 points max)
    git_score = 0
    if git_info["is_repo"]:
        git_score += 10
        if git_info["head"] != "n/a":
            git_score += 10
        else:
            reasons.append("Git repository is missing a HEAD commit")
            deductions.append(
                "[bold red]Git[/bold red] (-10 pts): repository lacks a HEAD commit.\n"
                "  [cyan]↳ Next Step:[/cyan] Create your first commit using [bold]git commit -m 'Initial commit'[/bold]."
            )
    else:
        reasons.append("Not a git repository (Initialize with `git init`)")
        deductions.append(
            "[bold red]Git[/bold red] (-20 pts): current folder is not a Git repository.\n"
            "  [cyan]↳ Next Step:[/cyan] Initialize Git by running [bold]git init[/bold] in your project directory."
        )

    # 3. Graph Intelligence (20 points max)
    graph_score = 0
    if graph_info["graphify_installed"]:
        graph_score += 10
        if graph_info["index_built"]:
            graph_score += 10
        else:
            reasons.append("Graphify index not built (Run `forge graph build`)")
            deductions.append(
                "[bold red]Graph Intelligence[/bold red] (-10 pts): Graphify index has not been built yet.\n"
                "  [cyan]↳ Next Step:[/cyan] Build the index by running [bold]forge graph build[/bold]."
            )
    else:
        reasons.append("Graphify not installed (Optional: `uv tool install graphifyy`)")
        deductions.append(
            "[bold red]Graph Intelligence[/bold red] (-20 pts): Graphify CLI is not installed.\n"
            "  [cyan]↳ Next Step:[/cyan] Install Graphify: [bold]uv tool install graphifyy[/bold]."
        )

    # 4. AI Providers (20 points max)
    providers_score = 0
    active_keys = sum(1 for val in api_status.values() if val)
    if active_keys > 0:
        providers_score += min(20, active_keys * 10)
    else:
        reasons.append("No AI Provider API keys found in environment variables")

    if providers_score < 20:
        deduct_pts = 20 - providers_score
        if providers_score == 0:
            deductions.append(
                "[bold red]AI Providers[/bold red] (-20 pts): no API keys configured.\n"
                "  [cyan]↳ Next Step:[/cyan] Add model API keys (e.g. export OPENAI_API_KEY='...') in your .env or shell."
            )
        else:
            deductions.append(
                "[bold red]AI Providers[/bold red] (-10 pts): only one API key configured.\n"
                "  [cyan]↳ Next Step:[/cyan] Optionally configure ANTHROPIC_API_KEY or GEMINI_API_KEY/GOOGLE_API_KEY for additional LLMs."
            )

    # 5. Repository State (20 points max)
    state_score = 0
    missing_req = report.missing_required
    if not missing_req:
        state_score += 10
    else:
        reasons.append(f"Missing required tools: {', '.join(d.name for d in missing_req)}")
        deductions.append(
            f"[bold red]Repository State[/bold red] (-10 pts): missing required tools ({', '.join(d.name for d in missing_req)}).\n"
            "  [cyan]↳ Next Step:[/cyan] Check the 'Dependency Guidance' section below to install missing tools."
        )

    if git_info["clean"]:
        state_score += 10
    else:
        reasons.append("Git repository has unstaged or uncommitted changes")
        deductions.append(
            "[bold red]Repository State[/bold red] (-10 pts): Git repository has uncommitted changes.\n"
            "  [cyan]↳ Next Step:[/cyan] Commit your work or run [bold]git stash[/bold] to clean the working directory."
        )

    total_score = config_score + git_score + graph_score + providers_score + state_score
    breakdown = {
        "Configuration": config_score,
        "Git": git_score,
        "Graph Intelligence": graph_score,
        "AI Providers": providers_score,
        "Repository State": state_score,
    }
    return total_score, breakdown, reasons, deductions


def _render_dashboard(
    platform: Any,
    paths: ProjectPaths,
    report: Any,
    api_status: dict[str, bool],
    git_info: dict[str, Any],
    graph_info: dict[str, Any],
    plugin_info: dict[str, Any],
    health_score: int,
    breakdown: dict[str, int],
    reasons: list[str],
    deductions: list[str],
) -> None:
    console = get_console()
    console.print()

    # Header Panel
    console.print(
        Panel(
            Align.center(
                f"[bold cyan]ForgeCLI[/bold cyan] [cyan]v{__version__}[/cyan]  •  [bold white]Developer Operating System[/bold white]"
            ),
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    # Health Score Column & Verdict
    if health_score >= 90:
        color = "green"
        status_text = "EXCELLENT"
    elif health_score >= 70:
        color = "yellow"
        status_text = "GOOD"
    else:
        color = "red"
        status_text = "NEEDS ATTENTION"

    score_bar = "█" * (health_score // 5) + "░" * (20 - health_score // 5)
    score_panel = Panel(
        Align.center(
            f"[bold {color}]{health_score}/100[/bold {color}]\n"
            f"[{color}]{score_bar}[/]\n\n"
            f"[bold {color}]Status: {status_text}[/]"
        ),
        title="[bold]Overall Health[/bold]",
        border_style=color,
        padding=(1, 2),
    )

    breakdown_lines = []
    for category, category_score in breakdown.items():
        filled = category_score // 2
        bar_char = "█" * filled + "░" * (10 - filled)
        cat_color = "green" if category_score >= 15 else "yellow" if category_score >= 10 else "red"
        breakdown_lines.append(f"[bold cyan]{category:<20}[/bold cyan] [bold white]{category_score:>2}/20[/bold white] [{cat_color}]{bar_char}[/]")

    breakdown_text = "\n".join(breakdown_lines)

    reasons_text = ""
    if reasons:
        reasons_text = "\n".join(f"[yellow]•[/yellow] {reason}" for reason in reasons[:5])
        if len(reasons) > 5:
            reasons_text += f"\n[dim]... and {len(reasons) - 5} more improvements[/dim]"
    else:
        reasons_text = "[green]✔ All checks passed perfectly! Your ForgeCLI workspace is fully ready.[/green]"

    deductions_text = ""
    if deductions:
        deductions_text = "\n[bold white]Deductions & Actionable Next Steps:[/bold white]\n" + "\n".join(f"• {d}" for d in deductions)
    else:
        deductions_text = "\n[bold green]✔ All categories are at maximum health score! No actions required.[/bold green]"

    verdict_content = (
        "[bold white]Weighted Category Breakdown:[/bold white]\n"
        f"{breakdown_text}\n\n"
        "[bold white]Readiness Diagnosis:[/bold white]\n"
        f"{reasons_text}\n"
        f"{deductions_text}"
    )

    verdict_panel = Panel(
        verdict_content,
        title="[bold]Diagnosis & Insights[/bold]",
        border_style="cyan" if health_score >= 70 else "yellow",
        padding=(1, 2),
    )

    console.print(Columns([score_panel, verdict_panel], equal=True))
    console.print()

    # Create detailed status grids
    t_platform = Table(title="💻 Platform & Paths", show_header=False, expand=True)
    t_platform.add_column("Key", style="dim cyan")
    t_platform.add_column("Value")
    t_platform.add_row("OS", platform.os.value)
    t_platform.add_row("Arch", platform.arch)
    t_platform.add_row("Python", python_version())
    t_platform.add_row("WSL", "yes" if platform.is_wsl else "no")
    t_platform.add_row("Config Dir", to_privacy_path(paths.config_dir))
    t_platform.add_row("Data Dir", to_privacy_path(paths.data_dir))

    t_providers = Table(title="🔑 AI Providers", show_header=True, expand=True)
    t_providers.add_column("Provider Key", style="cyan")
    t_providers.add_column("Status")
    t_providers.add_column("Action / Hint", style="dim")
    key_hints = {
        "OPENAI_API_KEY": "Get a key from platform.openai.com",
        "ANTHROPIC_API_KEY": "Get a key from console.anthropic.com",
        "GOOGLE_API_KEY": "Get a key from aistudio.google.com",
        "GEMINI_API_KEY": "Get a key from aistudio.google.com",
        "GROQ_API_KEY": "Get a key from console.groq.com",
        "MISTRAL_API_KEY": "Get a key from console.mistral.ai",
        "OPENROUTER_API_KEY": "Get a key from openrouter.ai",
    }
    for key, is_active in api_status.items():
        val = "[green]✔ Configured[/green]" if is_active else "[red]✘ Missing[/red]"
        hint = "[dim]Active & Ready[/dim]" if is_active else f"[yellow]{key_hints.get(key)}[/yellow]"
        t_providers.add_row(key, val, hint)

    console.print(Columns([Panel(t_platform, border_style="dim"), Panel(t_providers, border_style="dim")], equal=True))
    console.print()

    t_git = Table(title="📁 Git & Repository", show_header=False, expand=True)
    t_git.add_column("Key", style="dim cyan")
    t_git.add_column("Value")
    t_git.add_row("Is Git Repo", "[green]✔ Yes[/green]" if git_info["is_repo"] else "[red]✘ No[/red]")
    t_git.add_row("Branch", git_info["branch"])
    t_git.add_row("HEAD Commit", git_info["head"])
    t_git.add_row("Repo State", "[green]✔ Clean[/green]" if git_info["clean"] else "[yellow]⚠ Dirty[/yellow]")

    t_graph = Table(title="🕸 Repository Intelligence", show_header=False, expand=True)
    t_graph.add_column("Key", style="dim cyan")
    t_graph.add_column("Value")
    t_graph.add_row("Graphify CLI", "[green]✔ Installed[/green]" if graph_info["graphify_installed"] else "[red]✘ Missing[/red]")
    t_graph.add_row("Graph Index", "[green]✔ Built[/green]" if graph_info["index_built"] else "[yellow]✘ Not Built[/yellow]")
    if graph_info["index_built"]:
        size_kb = graph_info["index_size_bytes"] / 1024
        t_graph.add_row("Index Size", f"{size_kb:.2f} KB")

    t_plugins = Table(title="🔌 Plugins", show_header=False, expand=True)
    t_plugins.add_column("Key", style="dim cyan")
    t_plugins.add_column("Value")
    t_plugins.add_row("Total Installed", str(plugin_info["count"]))
    t_plugins.add_row("Active Plugins", str(plugin_info["enabled_count"]))
    if plugin_info["plugins"]:
        t_plugins.add_row("Loaded List", ", ".join(plugin_info["plugins"]))
    else:
        t_plugins.add_row("How to Install", "[dim]No active plugins found. Register plugins in pyproject.toml under [project.entry-points.\"forgecli.plugins\"] group.[/dim]")

    console.print(
        Columns(
            [Panel(t_git, border_style="dim"), Panel(t_graph, border_style="dim"), Panel(t_plugins, border_style="dim")],
            equal=True,
        )
    )
    console.print()

    # Detailed dependency hints if missing optional dependencies
    if report.missing:
        # Filter Homebrew for non-macOS systems
        missing_filtered = [d for d in report.missing if not (d.name == "brew" and platform.os != "macos")]
        if missing_filtered:
            console.print("[bold yellow]Dependency Guidance:[/bold yellow]")
            for dep in missing_filtered:
                hints = install_hint(dep.name)
                label = f"missing [bold]{dep.name}[/bold]"
                if dep.required:
                    label += " (required)"
                console.print(f"[yellow]![/yellow] {label}")
                for hint in hints:
                    console.print(f"    [dim]{hint}[/dim]")
            console.print()


__all__ = ["app"]
