"""``forgecli config`` subcommand group."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, table

app = typer.Typer(help="Inspect and validate ForgeCLI configuration.", no_args_is_help=True)


@app.command("show")
def show(
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to a forgecli.toml file."),
) -> None:
    """Print the resolved configuration (placeholder)."""
    from pathlib import Path

    context = bootstrap_context(config_path=Path(config_path) if config_path else None)
    try:
        settings = context.resolve_settings()
    except Exception as exc:
        error(f"Failed to load config: {exc}")
        raise typer.Exit(code=1) from exc

    rows: list[list[str]] = []
    for section_name, section in settings.model_dump().items():
        rows.append([section_name, str(section)])
    table(["Section", "Contents"], rows, title="ForgeCLI configuration")


@app.command("validate")
def validate(
    config_path: str | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Validate the configuration (placeholder)."""
    from pathlib import Path

    context = bootstrap_context(config_path=Path(config_path) if config_path else None)
    try:
        context.resolve_settings()
    except Exception as exc:
        error(f"Invalid configuration: {exc}")
        raise typer.Exit(code=1) from exc
    get_console().print("Configuration is valid.")


__all__ = ["app"]
