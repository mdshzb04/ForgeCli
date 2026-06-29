"""``forgecli plugin`` subcommand: install / enable / disable / update / doctor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from forgecli.cli.ui import error, get_console, info, success, table, warn
from forgecli.sdk import (
    PluginAlreadyInstalledError,
    PluginCompatibilityError,
    PluginError,
    PluginManager,
    PluginNotFoundError,
)


app = typer.Typer(
    help="Manage plugins (install, enable, disable, update, doctor).",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


def _manager(data_root: Path | None = None) -> PluginManager:
    if data_root is None:
        return PluginManager()
    return PluginManager(data_root=data_root)


@app.callback(invoke_without_command=True)
def plugin_cmd(
    ctx: typer.Context,
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root (tests)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    # No subcommand and no flags -> print help.
    get_console().print(ctx.get_help())


@app.command("list")
def list_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """List every installed plugin."""
    manager = _manager(data_root)
    rows: list[list[str]] = []
    for state, _loaded in manager.list():
        rows.append(
            [
                state.name,
                state.version,
                "yes" if state.enabled else "no",
                state.source,
                state.install_path or "-",
            ]
        )
    if json_output:
        sys.stdout.write(
            json.dumps(
                [
                    {
                        "name": s.name,
                        "version": s.version,
                        "enabled": s.enabled,
                        "source": s.source,
                        "install_path": s.install_path,
                    }
                    for s, _ in manager.list()
                ],
                indent=2,
            )
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        table(
            ["Plugin", "Version", "Enabled", "Source", "Path"],
            rows,
            title="Installed plugins",
        )


@app.command("install")
def install_cmd(
    source: str = typer.Argument(..., help="Path or git URL."),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Install a plugin from a local path or git URL."""
    manager = _manager(data_root)
    try:
        plugin = manager.install(source)
    except PluginAlreadyInstalledError as exc:
        error(f"{exc} is already installed")
        raise typer.Exit(code=1) from exc
    except PluginError as exc:
        error(f"install failed: {exc}")
        raise typer.Exit(code=1) from exc
    success(f"Installed {plugin.name} {plugin.version}.")


@app.command("enable")
def enable_cmd(
    name: str = typer.Argument(..., help="Plugin name."),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Enable an installed plugin."""
    manager = _manager(data_root)
    try:
        manager.enable(name)
    except PluginNotFoundError as exc:
        error(f"plugin not installed: {exc}")
        raise typer.Exit(code=1) from exc
    except PluginCompatibilityError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc
    except PluginError as exc:
        error(f"enable failed: {exc}")
        raise typer.Exit(code=1) from exc
    success(f"Enabled {name}.")


@app.command("disable")
def disable_cmd(
    name: str = typer.Argument(..., help="Plugin name."),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Disable an installed plugin."""
    manager = _manager(data_root)
    try:
        manager.disable(name)
    except PluginNotFoundError as exc:
        error(f"plugin not installed: {exc}")
        raise typer.Exit(code=1) from exc
    success(f"Disabled {name}.")


@app.command("uninstall")
def uninstall_cmd(
    name: str = typer.Argument(..., help="Plugin name."),
    keep_files: bool = typer.Option(
        False, "--keep-files", help="Only remove from the registry."
    ),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Uninstall a plugin (deletes its on-disk directory by default)."""
    manager = _manager(data_root)
    try:
        manager.uninstall(name, remove_files=not keep_files)
    except PluginNotFoundError as exc:
        error(f"plugin not installed: {exc}")
        raise typer.Exit(code=1) from exc
    success(f"Uninstalled {name}.")


@app.command("update")
def update_cmd(
    name: str = typer.Argument(..., help="Plugin name."),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Override the install source (path or git URL).",
    ),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Re-pull a plugin from its install source."""
    manager = _manager(data_root)
    try:
        plugin = manager.update(name, source=source)
    except PluginNotFoundError as exc:
        error(f"plugin not installed: {exc}")
        raise typer.Exit(code=1) from exc
    except PluginError as exc:
        error(f"update failed: {exc}")
        raise typer.Exit(code=1) from exc
    success(f"Updated {plugin.name} to {plugin.version}.")


@app.command("info")
def info_cmd(
    name: str = typer.Argument(..., help="Plugin name."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Print a plugin's manifest and lifecycle state."""
    manager = _manager(data_root)
    try:
        plugin = manager.get(name)
    except PluginNotFoundError as exc:
        error(f"plugin not found: {exc}")
        raise typer.Exit(code=1) from exc
    state = manager.state.plugins.get(name)
    if json_output:
        payload = plugin.manifest.to_dict()
        if state is not None:
            payload["state"] = {
                "enabled": state.enabled,
                "source": state.source,
                "installed_at": state.installed_at,
                "enabled_at": state.enabled_at,
                "config": state.config,
            }
        sys.stdout.write(json.dumps(payload, indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
        return
    rows: list[list[str]] = [
        ["Name", plugin.manifest.name],
        ["Version", str(plugin.manifest.version)],
        ["Summary", plugin.manifest.summary],
        ["Authors", ", ".join(plugin.manifest.authors) or "-"],
        ["License", plugin.manifest.license or "-"],
        ["Permissions", ", ".join(p.value for p in plugin.manifest.permissions) or "none"],
        ["Entry points", str(len(plugin.manifest.entry_points))],
    ]
    if state is not None:
        rows.extend(
            [
                ["Enabled", "yes" if state.enabled else "no"],
                ["Source", state.source],
                ["Installed at", state.installed_at or "-"],
            ]
        )
    table(["Field", "Value"], rows, title=plugin.manifest.name)


@app.command("doctor")
def doctor_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
    data_root: Optional[Path] = typer.Option(
        None, "--data-root", help="Override the SDK data root."
    ),
) -> None:
    """Run a health check across every installed plugin."""
    manager = _manager(data_root)
    reports = manager.doctor()
    if json_output:
        sys.stdout.write(
            json.dumps([report.to_dict() for report in reports], indent=2)
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return
    for report in reports:
        status = "[green]healthy[/green]" if report.healthy else "[red]unhealthy[/red]"
        info(f"{report.plugin_name}: {status}")
        for issue in report.issues:
            label = issue.severity.upper()
            get_console().print(f"    [{_severity_style(issue.severity)}]{label}[/] {issue.message}")
            if issue.suggestion:
                get_console().print(f"        [muted]→ {issue.suggestion}[/muted]")


def _severity_style(severity: str) -> str:
    return {
        "info": "cyan",
        "warn": "yellow",
        "error": "red",
    }.get(severity, "white")


__all__ = ["app"]
