"""``forge ask`` subcommand: ask a question about the project.

Wraps the :class:`AskWorkflow` so users can run a Q&A without
invoking the top-level ``forge`` command (which is the heavy
build pipeline). The output is a Rich-formatted answer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from forgecli.cli.ui import error, get_console, info, warn
from forgecli.orchestrator import (
    AskWorkflow,
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
)
from forgecli.providers.mock import MockProvider, MockProviderConfig
from forgecli.utils.paths import to_privacy_path

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
    live: bool = typer.Option(False, "--live", help="Use the real provider (default: mock)."),
) -> None:
    """Ask a question; print the answer to the terminal."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_ask(question, Path(path), live))


async def _run_ask(question: str, path: Path, live: bool) -> None:
    from forgecli.providers.base import Provider

    provider: Provider = MockProvider(MockProviderConfig())
    if live:
        from forgecli.cli.bootstrap import bootstrap_context
        from forgecli.providers.base import ProviderRegistry
        from forgecli.providers.router_state import load_state

        app_context = bootstrap_context(cwd=str(path))
        state = load_state(app_context.paths.data_dir / "router.json")
        registry: ProviderRegistry = app_context.container.resolve(ProviderRegistry)
        from forgecli.providers.anthropic import AnthropicConfig, AnthropicProvider
        from forgecli.providers.google import GeminiConfig, GeminiProvider
        from forgecli.providers.openai import OpenAIConfig, OpenAIProvider

        config = {
            "openai": OpenAIConfig(),
            "anthropic": AnthropicConfig(),
            "google": GeminiConfig(),
        }.get(state.choice)
        if config is not None:
            provider = (
                OpenAIProvider(config)
                if state.choice == "openai"
                else AnthropicProvider(config)
                if state.choice == "anthropic"
                else GeminiProvider(config)
            )

    registry = PluginRegistry()
    registry.register_classifier(HeuristicIntentClassifier())
    registry.register_workflow(AskWorkflow())
    orchestrator = Orchestrator(registry, provider=provider)

    try:
        if isinstance(provider, MockProvider):
            raise ValueError("No live provider configured")

        result = await orchestrator.run(question)
        if not result.success:
            raise Exception(result.error or "Orchestrator failed")

        get_console().print()
        get_console().print(result.summary or "(no answer)")
    except Exception as exc:
        # Fall back to local Graphify index
        from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
        backend = GraphifyRepositoryGraph(root=path)

        if await backend.is_available() and backend.artifacts.graph_json.exists():
            warn(f"Live provider could not be used ({exc}). Falling back to local Graphify index.")
            try:
                info("Searching local Graphify index for answers...")
                query_result = await backend.query(question)
                get_console().print()
                info("┌────────────────────────────────────────────────────────────┐")
                info("│ 🕸  Response sourced directly from local Graphify index     │")
                info("└────────────────────────────────────────────────────────────┘")
                get_console().print(query_result.answer or "(no answer found in graph)")
            except Exception as e:
                error(f"Failed to query local Graphify index: {e}")
                raise typer.Exit(code=1) from e
        else:
            warn(
                f"Live provider could not be used ({exc}) and no local Graphify index is available.\n"
                "To get answers, please set a valid API key (e.g. export OPENAI_API_KEY='...') or build a local graph index:\n"
                f"  - uv tool install graphifyy\n"
                f"  - forge graph build --path {to_privacy_path(path)}"
            )
            raise typer.Exit(code=1) from exc


__all__ = ["app"]


_ = Optional
