"""``forge explain`` top-level command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli.cli.ui import error, get_console, info, warn
from forgecli.orchestrator import (
    ExplainWorkflow,
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
)
from forgecli.providers.mock import MockProvider, MockProviderConfig
from forgecli.utils.paths import to_privacy_path

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
    live: bool = typer.Option(False, "--live", help="Use the real provider (default: mock)."),
) -> None:
    """Explain a node, file, or symbol using the Graphify knowledge graph and LLM."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_explain(target, Path(path), live))


async def _run_explain(target: str, path: Path, live: bool) -> None:
    from forgecli.providers.base import Provider

    provider: Provider = MockProvider(MockProviderConfig())
    if live:
        from forgecli.cli.bootstrap import bootstrap_context
        from forgecli.providers.base import ProviderRegistry
        from forgecli.providers.router_state import load_state

        app_context = bootstrap_context(cwd=str(path))
        state = load_state(app_context.paths.data_dir / "router.json")
        registry: ProviderRegistry = app_context.container.resolve(ProviderRegistry)

        chosen = state.choice or state.provider
        if not chosen:
            from forgecli.config.loader import ConfigLoader
            try:
                settings = ConfigLoader().load()
                chosen = settings.providers.default
            except Exception:
                pass
        if not chosen:
            raise ValueError(
                "No active provider configured. Please authenticate first (e.g. 'forge auth login'), "
                "then set your active provider using 'forge provider use <provider>' and active model using 'forge model use <model>'."
            )

        if not registry.has(chosen):
            raise ValueError(f"Unknown provider '{chosen}'.")
        provider_cls = registry.get(chosen)
        provider = provider_cls()  # type: ignore[call-arg]

    plugin_registry = PluginRegistry()
    plugin_registry.register_classifier(HeuristicIntentClassifier())
    plugin_registry.register_workflow(ExplainWorkflow())
    orchestrator = Orchestrator(plugin_registry, provider=provider)

    try:
        if isinstance(provider, MockProvider):
            raise ValueError("No live provider configured")

        result = await orchestrator.run(target)
        if not result.success:
            raise Exception(result.error or "Orchestrator failed")

        get_console().print()
        get_console().print(result.summary or "(no explanation)")
    except Exception as exc:
        warn(f"Live provider could not be used ({exc}). Falling back to local search.")
        from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
        backend = GraphifyRepositoryGraph(root=path)
        if await backend.is_available() and backend.artifacts.graph_json.exists():
            try:
                info("Searching local Graphify index...")
                query_result = await backend.explain(target)
                get_console().print()
                get_console().print(query_result.explanation or "(no explanation found in graph)")
            except Exception as e:
                error(f"Failed to query local Graphify index: {e}")
                raise typer.Exit(code=1) from e
        else:
            warn(
                f"Live provider could not be used ({exc}) and no local Graphify index is available.\n"
                "To get explanation, please set a valid API key (e.g. export OPENAI_API_KEY='...') or build a local graph index:\n"
                f"  - uv tool install graphifyy\n"
                f"  - forge graph build --path {to_privacy_path(path)}"
            )
            raise typer.Exit(code=1) from exc


__all__ = ["app"]
