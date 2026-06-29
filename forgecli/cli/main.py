"""Top-level Typer application for ForgeCLI."""

from __future__ import annotations

from pathlib import Path

import typer

from forgecli import __app_name__, __version__
from forgecli.cli import (
    commands_build,
    commands_config,
    commands_explain,
    commands_git,
    commands_graph,
    commands_history,
    commands_index,
    commands_init,
    commands_model,
    commands_optimizer,
    commands_plan,
    commands_providers,
    commands_review,
)
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console
from forgecli.core.errors import ForgeCLIError

app = typer.Typer(
    name=__app_name__,
    help="ForgeCLI - AI Development Operating System.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

app.add_typer(commands_init.app, name="init")
app.add_typer(commands_config.app, name="config")
app.add_typer(commands_providers.app, name="providers")
app.add_typer(commands_model.app, name="model")
app.add_typer(commands_index.app, name="index")
app.add_typer(commands_graph.app, name="graph")
app.add_typer(commands_optimizer.app, name="optimizer")
app.add_typer(commands_plan.app, name="plan")
app.add_typer(commands_build.app, name="build")
app.add_typer(commands_review.app, name="review")
app.add_typer(commands_git.app, name="git")
app.add_typer(commands_history.app, name="history")
app.add_typer(commands_explain.app, name="explain")


def _version_callback(value: bool) -> None:
    if value:
        get_console().print(f"{__app_name__} [muted]v{__version__}[/muted]")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a forgecli.toml file.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """ForgeCLI global options.

    These options are available to every subcommand.
    """
    extras: dict[str, object] = {"verbose": verbose}
    context = bootstrap_context(config_path=config, extras=extras)
    ctx.obj = context


def _run() -> None:
    """Run the Typer app and translate ForgeCLIError to clean exit codes."""
    try:
        app()
    except ForgeCLIError as exc:
        error(str(exc))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    _run()


__all__ = ["app", "main"]
