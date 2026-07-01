"""``forge docs`` subcommand: auto-generate project documentation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, warn
from forgecli.docs.generator import generate_docs
from forgecli.orchestrator import (
    DocsWorkflow,
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
)

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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
) -> None:
    """Generate an overview of the current project."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_docs(Path(path), output, live, verbose))


async def _run_docs(path: Path, output: Path | None, live: bool, verbose: bool = False) -> None:
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    from forgecli.providers.mock import MockProvider

    provider, decision = resolve_provider_and_decision(live=live, cwd=path)

    if isinstance(provider, MockProvider) and not live:
        console = get_console()
        console.print("[yellow]⚠ Offline Mode[/yellow]\n")
        console.print("Using Forge's built-in mock AI.\n")
        console.print("Run:\n")
        console.print("  forge docs --live\n")
        console.print("to use your configured provider.\n")

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

        from forgecli.cli.ui import table
        console = get_console()
        console.print("[bold green]✓ Documentation generated[/bold green]\n")
        console.print("────────────────────────────────────────────\n")

        dest = output or Path("docs/OVERVIEW.md")
        dest_path = path / dest
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(result.summary or "", encoding="utf-8")

        from rich import box
        from rich.panel import Panel
        from rich.syntax import Syntax

        console.print(f"📄 {dest}\n")
        syntax = Syntax((result.summary or "").rstrip(), "markdown", theme="monokai")
        panel = Panel(
            syntax,
            border_style="orange3",
            box=box.ROUNDED,
            expand=False,
        )
        console.print(panel)
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
            console.print("[bold]Output Files[/bold]")
            console.print(str(dest))
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
        warn(f"Live provider could not be used ({exc}). Falling back to static documentation generator.")
        try:
            context = bootstrap_context(cwd=str(path))
            target = generate_docs(context, output=output)

            console = get_console()
            console.print("[bold green]✓ Documentation generated[/bold green]\n")
            console.print("────────────────────────────────────────────\n")

            rel_target = target.relative_to(path) if path in target.parents else target
            console.print(f"📄 {rel_target}\n")

            from rich import box
            from rich.panel import Panel
            from rich.syntax import Syntax
            try:
                content = target.read_text(encoding="utf-8")
            except Exception:
                content = ""
            syntax = Syntax(content.rstrip(), "markdown", theme="monokai")
            panel = Panel(
                syntax,
                border_style="orange3",
                box=box.ROUNDED,
                expand=False,
            )
            console.print(panel)
            console.print()

            if verbose:
                console.print("[bold]Provider[/bold]")
                console.print("Static Scanner")
                console.print()
                console.print("[bold]Output Files[/bold]")
                console.print(str(rel_target))
                console.print()
                console.print("────────────────────────────────────────")
        except Exception as e:
            error(f"Failed to generate docs: {e}")
            raise typer.Exit(code=1) from None


__all__ = ["app"]
