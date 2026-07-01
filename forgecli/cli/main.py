"""Top-level Typer application for ForgeCLI."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import warnings
from pathlib import Path

import typer

from forgecli import __app_name__, __version__
from forgecli.cli import (
    commands_ask,
    commands_auth,
    commands_build,
    commands_commit,
    commands_config,
    commands_docs,
    commands_doctor,
    commands_explain,
    commands_graph,
    commands_history,
    commands_index,
    commands_info,
    commands_init,
    commands_model,
    commands_plan,
    commands_plugin,
    commands_providers,
    commands_release,
    commands_review,
    commands_status,
    commands_update,
)
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.commands_forge import run_forge as _run_forge_impl
from forgecli.cli.ui import error, get_console, warn
from forgecli.core.errors import ForgeCLIError

# Suppress all runtime warnings globally to present a clean, production-grade CLI.
warnings.filterwarnings("ignore")

with contextlib.suppress(AttributeError):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

app = typer.Typer(
    name=__app_name__,
    help="ForgeCLI - AI Development Operating System.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
)

app.add_typer(commands_init.app, name="init")
app.add_typer(commands_config.app, name="config")
app.add_typer(commands_auth.app, name="auth")
app.add_typer(commands_providers.app, name="providers")
app.add_typer(commands_providers.app, name="provider")
app.add_typer(commands_model.app, name="model")
app.add_typer(commands_index.app, name="index")
app.add_typer(commands_graph.app, name="graph")
app.add_typer(commands_plan.app, name="plan")
app.command(
    "build",
    help="Build code changes based on a prompt.",
    context_settings={"allow_interspersed_args": True},
)(commands_build.build_cmd)

app.add_typer(commands_commit.app, name="commit")
app.add_typer(commands_review.app, name="review")

app.command(
    "ask",
    help="Ask a question about the repository.",
    context_settings={"allow_interspersed_args": True},
)(commands_ask.ask_cmd)

app.add_typer(commands_docs.app, name="docs")

app.command(
    "release",
    help="Cut a release (changelog promotion, tag, optional push).",
    context_settings={"allow_interspersed_args": True},
)(commands_release.release_cmd)

app.add_typer(commands_history.app, name="history")

app.command(
    "explain",
    help="Explain a file or symbol.",
    context_settings={"allow_interspersed_args": True},
)(commands_explain.main)


app.add_typer(commands_doctor.app, name="doctor")
app.add_typer(commands_plugin.app, name="plugin")
app.add_typer(commands_status.app, name="status")
app.add_typer(commands_info.app, name="info")
app.add_typer(commands_update.app, name="update")


# Wrap click's invoke method to record history for all commands
try:
    import typer.main
    original_get_command = typer.main.get_command

    def wrapped_get_command(typer_instance):
        click_command = original_get_command(typer_instance)
        if typer_instance is app:
            original_invoke = click_command.invoke

            def wrapped_invoke(ctx):
                import sys
                import time

                from forgecli.cli.bootstrap import bootstrap_context
                from forgecli.memory.history import HistoryRepository
                from forgecli.memory.store import MemoryStore

                start_time = time.time()
                success = True
                err_msg = None
                try:
                    return original_invoke(ctx)
                except Exception as exc:
                    success = False
                    err_msg = str(exc)
                    raise
                except BaseException as exc:
                    success = False
                    err_msg = str(exc)
                    raise
                finally:
                    cmd = " ".join(sys.argv)
                    if len(sys.argv) > 0 and ("pytest" in sys.argv[0] or "py.test" in sys.argv[0]):
                        cmd = ctx.command_path
                        if ctx.invoked_subcommand:
                            cmd += " " + ctx.invoked_subcommand
                        if ctx.args:
                            cmd += " " + " ".join(ctx.args)

                    is_history_list = "history" in cmd
                    is_help = "--help" in cmd or "-h" in cmd or (ctx.invoked_subcommand == "help" if ctx.invoked_subcommand else False)
                    is_version = "--version" in cmd or "-v" in cmd or "--check-update" in cmd

                    if not (is_history_list or is_help or is_version or (len(sys.argv) < 2 and "pytest" not in sys.argv[0])):
                        try:
                            context = bootstrap_context()
                            store = context.container.resolve(MemoryStore)
                            provider = None
                            model = None
                            try:
                                from forgecli.providers.router_state import load_state
                                state = load_state(context.paths.data_dir / "router.json")
                                if state.choice:
                                    provider = state.provider
                                    model = state.model
                            except Exception:
                                pass

                            duration_ms = int((time.time() - start_time) * 1000)
                            with store:
                                history = HistoryRepository(store)
                                history.record(
                                    command=cmd,
                                    provider=provider,
                                    model=model,
                                    duration_ms=duration_ms,
                                    success=success,
                                    error=err_msg,
                                )
                        except Exception:
                            pass

            click_command.invoke = wrapped_invoke
        return click_command

    typer.main.get_command = wrapped_get_command
    try:
        import typer.testing
        typer.testing._get_command = wrapped_get_command
    except Exception:
        pass
except Exception as e:
    print(f"DEBUG: monkeypatch failed with {e}", file=sys.stderr)
    pass


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
        if "404" in info.error:
            warn("could not check for updates: ForgeCLI is not published to PyPI yet (development installation).")
        else:
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
    diff: bool = typer.Option(False, "--diff", "-d", help="Show unified git diff."),
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
    runs the full build pipeline. With a subcommand, ForgeCLI
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
        # No --prompt and no subcommand: show premium dashboard startup banner.
        console = get_console()
        console.print()
        console.print(
            "  [bold cyan]_____   ___  ____   ____ _____  ____ _     ___ [/bold cyan]\n"
            "  [bold cyan]|  ___| / _ \\|  _ \\ / ___| ____|/ ___| |   |_ _|[/bold cyan]\n"
            "  [bold cyan]| |_   | | | | |_) | |  _|  _| | |   | |    | | [/bold cyan]\n"
            "  [bold cyan]|  _|  | |_| |  _ <| |_| | |___| |___| |___ | | [/bold cyan]\n"
            "  [bold cyan]|_|     \\___/|_| \\_\\\\____|_____|\\____|_____|___|[/bold cyan]\n"
        )
        console.print(
            f"  [bold cyan]ForgeCLI[/bold cyan] [dim]v{__version__}[/dim] • [bold white]Developer Operating System[/bold white]"
        )
        console.print(
            "  [dim]Orchestrates codebase intelligence and LLMs.[/dim]\n"
        )
        console.print(
            "  [bold]Usage:[/bold]\n"
            "    [cyan]forge --prompt \"<your request>\"[/cyan]  Run the AI developer pipeline\n"
            "    [cyan]forge status[/cyan]                      Show current project and tool status\n"
            "    [cyan]forge doctor[/cyan]                      Run diagnostic checks and self-checks\n"
            "    [cyan]forge --help[/cyan]                      List all available subcommands\n"
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
                verbose=verbose,
                diff=diff,
            )
        )
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"forge: {exc}")
        raise typer.Exit(code=1) from exc


def _run() -> None:
    """Run the Typer app and translate ForgeCLIError to clean exit codes."""
    import sys
    import time

    from forgecli.cli.bootstrap import bootstrap_context
    from forgecli.memory.history import HistoryRepository
    from forgecli.memory.store import MemoryStore

    start_time = time.time()
    cmd = " ".join(sys.argv)

    is_history_list = len(sys.argv) >= 2 and sys.argv[1] == "history"
    is_help = "--help" in sys.argv or "-h" in sys.argv
    is_version = "--version" in sys.argv or "-v" in sys.argv or "--check-update" in sys.argv

    success = True
    err_msg = None
    try:
        app()
    except ForgeCLIError as exc:
        success = False
        err_msg = str(exc)
        error(str(exc))
        raise SystemExit(2) from exc
    except SystemExit as exc:
        if exc.code != 0:
            success = False
            err_msg = f"Exit code: {exc.code}"
        raise
    except BaseException as exc:
        success = False
        err_msg = str(exc)
        raise
    finally:
        if not (is_history_list or is_help or is_version or len(sys.argv) < 2):
            try:
                context = bootstrap_context()
                store = context.container.resolve(MemoryStore)
                provider = None
                model = None
                try:
                    from forgecli.providers.router_state import load_state
                    state = load_state(context.paths.data_dir / "router.json")
                    if state.choice:
                        provider = state.provider
                        model = state.model
                except Exception:
                    pass

                duration_ms = int((time.time() - start_time) * 1000)
                with store:
                    history = HistoryRepository(store)
                    history.record(
                        command=cmd,
                        provider=provider,
                        model=model,
                        duration_ms=duration_ms,
                        success=success,
                        error=err_msg,
                    )
            except Exception:
                pass


if __name__ == "__main__":
    _run()


__all__ = ["app", "main"]
