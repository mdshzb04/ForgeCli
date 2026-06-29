"""``forgecli doctor`` subcommand: run a self-check.

Diagnoses the current host (OS, dependencies, config) and prints a
human-readable report. Useful in CI to verify that a fresh
machine has everything it needs to run ForgeCLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from forgecli import __version__
from forgecli.cli.ui import (
    error,
    get_console,
    info,
    success,
    table,
    warn,
)
from forgecli.platform import (
    ProjectPaths,
    check_dependencies,
    current_platform,
    install_hint,
    load_dotenv,
    python_version,
)
from forgecli.platform.deps import DependencyStatus


app = typer.Typer(
    help="Diagnose the current host (OS, dependencies, configuration).",
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

    if json_output:
        payload = {
            "forge_version": __version__,
            "platform": platform.os.value,
            "arch": platform.arch,
            "python": python_version(),
            "is_wsl": platform.is_wsl,
            "config_dir": str(paths.config_dir),
            "data_dir": str(paths.data_dir),
            "dependencies": report.to_dict(),
        }
        sys.stdout.write(json.dumps(payload, indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        _render_human(platform, paths, report)

    if strict and report.missing_required:
        missing = ", ".join(d.name for d in report.missing_required)
        error(f"Required dependencies are missing: {missing}")
        raise typer.Exit(code=1)
    if report.missing:
        success("ForgeCLI can run, but optional dependencies are missing.")
    else:
        success("ForgeCLI self-check passed.")


def _render_human(platform, paths: ProjectPaths, report) -> None:
    console = get_console()
    console.print()
    console.print(f"[bold]Forge {__version__}[/bold] — self check")
    console.print()
    rows = [
        ["OS", platform.os.value],
        ["Arch", platform.arch],
        ["Release", platform.release or "(unknown)"],
        ["Python", python_version()],
        ["WSL", "yes" if platform.is_wsl else "no"],
        ["Config dir", str(paths.config_dir)],
        ["Data dir", str(paths.data_dir)],
    ]
    table(["Field", "Value"], rows, title="Platform")
    console.print()

    dep_rows: list[list[str]] = []
    for dep in report.dependencies:
        status_label = dep.status.value
        if dep.status is DependencyStatus.MISSING:
            status_label = f"[red]{status_label}[/red]"
        else:
            status_label = f"[green]{status_label}[/green]"
        dep_rows.append(
            [
                dep.name + (" (required)" if dep.required else ""),
                status_label,
                dep.version or "—",
                dep.path or "—",
            ]
        )
    table(
        ["Dependency", "Status", "Version", "Path"],
        dep_rows,
        title="Dependencies",
    )
    console.print()

    if report.missing:
        for dep in report.missing:
            hints = install_hint(dep.name)
            label = f"missing [bold]{dep.name}[/bold]"
            if dep.required:
                label += " (required)"
            console.print(f"[yellow]![/yellow] {label}")
            for hint in hints:
                console.print(f"    [muted]{hint}[/muted]")
        console.print()
    else:
        success("All dependencies present.")


__all__ = ["app"]


# Silence the unused-import warning for ``info`` (kept for future).
_ = info
_ = Optional
