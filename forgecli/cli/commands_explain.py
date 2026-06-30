"""``forge explain`` top-level command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli.cli.ui import error, get_console
from forgecli.orchestrator import (
    ExplainWorkflow,
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
)

app = typer.Typer(
    help="Explain a node, file, or symbol using the Graphify knowledge graph and LLM.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Node label, id, or filename to explain."),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    live: bool = typer.Option(True, "--live/--mock", help="Use the real provider chosen by the router (default: True)."),
) -> None:
    """Explain a node, file, or symbol using the Graphify knowledge graph and LLM."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_explain(target, Path(path), live))


async def _run_explain(target: str, path: Path, live: bool) -> None:
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    from forgecli.providers.mock import MockProvider

    provider, decision = resolve_provider_and_decision(live=live, cwd=path)

    if isinstance(provider, MockProvider) and not live:
        from forgecli.cli.ui import info
        info("Offline mode: using the mock provider. Pass --live to use the real one.")

    plugin_registry = PluginRegistry()
    plugin_registry.register_classifier(HeuristicIntentClassifier())
    plugin_registry.register_workflow(ExplainWorkflow())
    orchestrator = Orchestrator(plugin_registry, provider=provider, decision=decision)

    try:
        from forgecli.plugins import Intent
        result = await orchestrator.run(target, intent=Intent.EXPLAIN)
        if not result.success:
            raise Exception(result.error or "Orchestrator failed")

        get_console().print()
        get_console().print(result.summary or "(no explanation)")
    except Exception as exc:
        error(f"Failed to get explanation from provider: {exc}")
        raise typer.Exit(code=1) from None


__all__ = ["app"]
