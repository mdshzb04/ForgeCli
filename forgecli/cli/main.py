"""Top-level Typer application for ForgeCLI."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli import __app_name__, __version__
from forgecli.cli import (
    commands_ask,
    commands_build,
    commands_commit,
    commands_config,
    commands_doctor,
    commands_docs,
    commands_explain,
    commands_forge,
    commands_git,
    commands_graph,
    commands_history,
    commands_index,
    commands_init,
    commands_model,
    commands_optimizer,
    commands_plan,
    commands_plugin,
    commands_providers,
    commands_release,
    commands_review,
)
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.commands_forge import run_forge as _run_forge_impl
from forgecli.cli.ui import error, get_console, warn
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
app.add_typer(commands_commit.app, name="commit")
app.add_typer(commands_review.app, name="review")
app.add_typer(commands_ask.app, name="ask")
app.add_typer(commands_docs.app, name="docs")
app.add_typer(commands_release.app, name="release")
app.add_typer(commands_git.app, name="git")
app.add_typer(commands_history.app, name="history")
app.add_typer(commands_explain.app, name="explain")
app.add_typer(commands_doctor.app, name="doctor")
app.add_typer(commands_plugin.app, name="plugin")


def _version_callback(value: bool) -> None:
    if value:
        get_console().print(f"{__app_name__} [muted]v{__version__}[/muted]")
        raise typer.Exit()


def _check_update_callback(value: bool) -> None:
    """Query PyPI for the latest version and print a single line."""
    if not value:
        return
    from forgecli.platform import check_for_update, upgrade_command

    info = check_for_update()
    if info.error and info.latest is None:
        warn(f"could not check for updates: {info.error}")
    elif info.update_available:
        warn(
            f"update available: {info.current} -> {info.latest}\n"
            f"  upgrade with: {upgrade_command()}"
        )
    elif info.latest:
        get_console().print(f"{__app_name__} [muted]v{__version__} (up to date)[/muted]")
    else:
        get_console().print(f"{__app_name__} [muted]v{__version__}[/muted]")
    raise typer.Exit()


# Top-level `forge --prompt "<request>"` callback: dispatches to the
# orchestrator. This is the headline command.
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Natural-language description of what to build, ask, plan, etc.",
    ),
    path: str = typer.Option(".", "--path", help="Project root."),
    live: bool = typer.Option(
        False, "--live", help="Use the real provider chosen by the router (default: mock)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit a JSON summary."),
    save_diff: Path | None = typer.Option(
        None, "--save-diff", help="Write the produced diff to this path."
    ),
    no_commit: bool = typer.Option(
        False, "--no-commit", help="Skip the auto-commit step."
    ),
    no_tests: bool = typer.Option(
        False, "--no-tests", help="Skip the test stage."
    ),
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
    check_update: bool = typer.Option(
        False,
        "--check-update",
        callback=_check_update_callback,
        is_eager=True,
        help="Check PyPI for a newer version and exit.",
    ),
) -> None:
    """ForgeCLI global entry point.

    With ``--prompt "<request>"`` (no subcommand) the orchestrator
    runs the full Graphify -> Ponytail -> LLM -> apply -> test ->
    auto-fix -> summary pipeline. With a subcommand, ForgeCLI
    dispatches to that subcommand.
    """
    extras: dict[str, object] = {"verbose": verbose}
    bootstrap_context(config_path=config, extras=extras)
    if version:  # _version_callback raises typer.Exit
        return
    # If a subcommand was invoked, let it handle the request.
    if ctx.invoked_subcommand is not None:
        return
    if not prompt:
        # No --prompt and no subcommand: show help.
        get_console().print(
            'Usage: forge --prompt "<your request>"  -- see `forge --help`.'
        )
        return
    text = prompt.strip()
    try:
        asyncio.run(
            _run_forge_impl(
                text,
                Path(path).resolve(),
                live=live,
                json_output=json_output,
                save_diff=save_diff,
                no_commit=no_commit,
                no_tests=no_tests,
            )
        )
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"forge: {exc}")
        raise typer.Exit(code=1) from exc


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
