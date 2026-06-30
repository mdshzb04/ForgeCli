"""``forgecli config`` subcommand group."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, table

app = typer.Typer(
    help="Inspect and validate ForgeCLI configuration.",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context) -> None:
    """Inspect and validate ForgeCLI configuration."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(show, config_path=None)


@app.command("show")
def show(
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to a forgecli.toml file."),
) -> None:
    """Print the resolved configuration."""
    from pathlib import Path

    context = bootstrap_context(config_path=Path(config_path) if config_path else None)
    try:
        settings = context.resolve_settings()
    except Exception as exc:
        error(f"Failed to load config: {exc}")
        raise typer.Exit(code=1) from exc

    def _expand_paths(val: Any) -> Any:
        from pathlib import Path
        if isinstance(val, dict):
            return {k: _expand_paths(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_expand_paths(item) for item in val]
        if isinstance(val, Path):
            return str(val.expanduser())
        if isinstance(val, str) and (val.startswith("~/") or val == "~"):
            return str(Path(val).expanduser())
        return val

    from typing import Any
    rows: list[list[str]] = []
    for section_name, section in settings.model_dump().items():
        rows.append([section_name, str(_expand_paths(section))])
    table(["Section", "Contents"], rows, title="ForgeCLI configuration")


@app.command("validate")
def validate(
    config_path: str | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Validate the configuration."""
    from pathlib import Path

    context = bootstrap_context(config_path=Path(config_path) if config_path else None)
    try:
        context.resolve_settings()
    except Exception as exc:
        error(f"Invalid configuration: {exc}")
        raise typer.Exit(code=1) from exc
    get_console().print("Configuration is valid.")


__all__ = ["app"]
