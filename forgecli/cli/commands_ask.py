"""``forge ask`` subcommand: ask a question about the project.

Wraps the :class:`AskWorkflow` so users can run a Q&A without
invoking the top-level ``forge`` command (which is the heavy
build pipeline). The output is a Rich-formatted answer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli.cli.ui import error, get_console
from forgecli.orchestrator import (
    AskWorkflow,
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
)

app = typer.Typer(
    help="Ask a question about the repository (uses Graphify + Ponytail + LLM).",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def ask_cmd(
    ctx: typer.Context,
    question: str = typer.Argument(..., help="Question to ask about the project."),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    live: bool = typer.Option(True, "--live/--mock", help="Use the real provider chosen by the router (default: True)."),
) -> None:
    """Ask a question; print the answer to the terminal."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_ask(question, Path(path), live))


async def _run_ask(question: str, path: Path, live: bool) -> None:
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    from forgecli.providers.mock import MockProvider

    provider, decision = resolve_provider_and_decision(live=live, cwd=path)

    if isinstance(provider, MockProvider) and not live:
        from forgecli.cli.ui import info
        info("Offline mode: using the mock provider. Pass --live to use the real one.")

    plugin_registry = PluginRegistry()
    plugin_registry.register_classifier(HeuristicIntentClassifier())
    plugin_registry.register_workflow(AskWorkflow())
    orchestrator = Orchestrator(plugin_registry, provider=provider, decision=decision)

    try:
        from forgecli.plugins import Intent
        result = await orchestrator.run(question, intent=Intent.ASK)
        if not result.success:
            raise Exception(result.error or "Orchestrator failed")

        get_console().print()
        get_console().print(result.summary or "(no answer)")
    except Exception as exc:
        error(f"Failed to get answer from provider: {exc}")
        raise typer.Exit(code=1) from None


__all__ = ["app"]
