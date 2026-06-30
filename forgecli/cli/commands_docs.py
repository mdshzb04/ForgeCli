"""``forge docs`` subcommand: auto-generate project documentation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, success, warn
from forgecli.docs.generator import generate_docs
from forgecli.orchestrator import (
    DocsWorkflow,
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
)
from forgecli.providers.mock import MockProvider, MockProviderConfig

app = typer.Typer(
    help="Auto-generate a project overview from the knowledge graph.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def docs_cmd(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Override the output file (default: docs/OVERVIEW.md)."
    ),
    live: bool = typer.Option(False, "--live", help="Use the real provider (default: mock)."),
) -> None:
    """Generate an overview of the current project."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_docs(Path(path), output, live))


async def _run_docs(path: Path, output: Path | None, live: bool) -> None:
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    from forgecli.providers.mock import MockProvider

    provider, decision = resolve_provider_and_decision(live=live, cwd=path)

    plugin_registry = PluginRegistry()
    plugin_registry.register_classifier(HeuristicIntentClassifier())
    plugin_registry.register_workflow(DocsWorkflow())
    orchestrator = Orchestrator(plugin_registry, provider=provider, decision=decision)

    try:
        if isinstance(provider, MockProvider):
            raise ValueError("No live provider configured")

        result = await orchestrator.run("generate documentation")
        if not result.success:
            raise Exception(result.error or "Orchestrator failed")

        get_console().print()
        get_console().print(result.summary or "(no summary)")
    except Exception as exc:
        warn(f"Live provider could not be used ({exc}). Falling back to static documentation generator.")
        try:
            context = bootstrap_context(cwd=str(path))
            target = generate_docs(context, output=output)
            success(f"Documentation written to {target}")
            get_console().print(f"  [muted]{target}[/muted]")
        except Exception as e:
            error(f"Failed to generate docs: {e}")
            raise typer.Exit(code=1) from None


__all__ = ["app"]
