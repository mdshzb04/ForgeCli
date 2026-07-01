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
    help="Explain a file or symbol.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Node label, id, or filename to explain."),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    live: bool = typer.Option(True, "--live/--mock", help="Use the real provider chosen by the router (default: True)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
) -> None:
    """Explain a file or symbol."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_explain(target, Path(path), live, verbose))


async def _run_explain(target: str, path: Path, live: bool, verbose: bool = False) -> None:
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    from forgecli.providers.mock import MockProvider

    provider, decision = resolve_provider_and_decision(live=live, cwd=path)

    if isinstance(provider, MockProvider) and not live:
        console = get_console()
        console.print("[yellow]⚠ Offline Mode[/yellow]\n")
        console.print("Using Forge's built-in mock AI.\n")
        console.print("Run:\n")
        console.print("  forge explain --live\n")
        console.print("to use your configured provider.\n")

    plugin_registry = PluginRegistry()
    plugin_registry.register_classifier(HeuristicIntentClassifier())
    plugin_registry.register_workflow(ExplainWorkflow())
    orchestrator = Orchestrator(plugin_registry, provider=provider, decision=decision)

    try:
        from forgecli.plugins import Intent
        result = await orchestrator.run(target, intent=Intent.EXPLAIN)
        if not result.success:
            raise Exception(result.error or "Orchestrator failed")

        from rich.markdown import Markdown

        from forgecli.cli.ui import table
        console = get_console()
        console.print("[bold green]✓ Explanation generated[/bold green]\n")
        console.print("────────────────────────────────────────────\n")
        if result.summary:
            console.print(Markdown(result.summary.strip()))
        else:
            console.print("(no explanation)")
        console.print()

        if verbose:
            provider_name = decision.provider_name if decision else "mock"
            provider_map = {
                "mock": "Mock (Offline)",
                "openai": "OpenAI (Live)",
                "anthropic": "Anthropic (Live)",
                "google": "Gemini (Live)",
                "gemini": "Gemini (Live)",
            }
            provider_str = provider_map.get(provider_name.lower(), f"{provider_name.title()} (Live)")

            console.print("[bold]Provider[/bold]")
            console.print(provider_str)
            console.print()
            console.print("[bold]Optimizer[/bold]")
            console.print("Ponytail (Ultra)")
            console.print()
            console.print("[bold]Time[/bold]")
            console.print(f"{result.duration_seconds:.1f} seconds")
            console.print()

            if result.stages:
                console.print("[bold yellow]=== Pipeline Stages timings ===[/bold yellow]\n")
                rows = []
                for s in result.stages:
                    rows.append([
                        str(s.get("name", "Stage")),
                        str(s.get("status", "succeeded")),
                        f"{float(s.get('duration_seconds') or 0.0):.3f}s",
                        str(s.get("error") or "—")
                    ])
                table(["Stage", "Status", "Duration", "Error"], rows, title="Pipeline stages")
                console.print()
            console.print("────────────────────────────────────────")
    except Exception as exc:
        error(f"Failed to get explanation from provider: {exc}")
        raise typer.Exit(code=1) from None


__all__ = ["app"]
