"""``forge graph`` subcommand group: build / query / explain.

These commands integrate the external Graphify CLI behind the
:mod:`forgecli.graph.repository` abstraction. When Graphify is not
installed the commands print an installation hint instead of failing.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from forgecli.cli.ui import (
    error,
    get_console,
    info,
    success,
    warn,
)
from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
from forgecli.utils.paths import to_privacy_path

app = typer.Typer(
    help="Build, query, and traverse the repository knowledge graph (Graphify).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _build_backend(path: Path) -> GraphifyRepositoryGraph:
    return GraphifyRepositoryGraph(root=path)


async def _require_graphify(backend: GraphifyRepositoryGraph) -> None:
    if not await backend.is_available():
        raise typer.Exit(code=1) from None


def setup_graphify_credentials(path: Path) -> str | None:
    """Read the active provider, load its API key, set env vars, and return provider name if configured."""
    from forgecli.cli.bootstrap import bootstrap_context
    from forgecli.core.credentials import get_api_key
    from forgecli.providers.router import _PROVIDER_ENV_VARS, ModelRouter
    from forgecli.providers.router_state import load_state as load_router_state

    app_context = bootstrap_context(cwd=path)
    state = load_router_state(app_context.paths.data_dir / "router.json")
    router = app_context.container.resolve(ModelRouter)
    decision = router.select(state.choice)

    provider_name = decision.provider_name
    if provider_name == "mock":
        return None

    # Try env vars first
    env_vars = _PROVIDER_ENV_VARS.get(provider_name, ())
    for ev in env_vars:
        if os.environ.get(ev):
            return provider_name

    # Try keychain/credential manager
    api_key = get_api_key(provider_name)
    if api_key:
        for ev in env_vars:
            os.environ[ev] = api_key
        return provider_name

    return None


@app.command("build")
def build_cmd(
    path: str = typer.Option(".", "--path", "-p", help="Project root to index."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite graph.json even if the rebuild has fewer nodes.",
    ),
    no_cluster: bool = typer.Option(
        False, "--no-cluster", help="Skip Leiden clustering."
    ),
) -> None:
    """Build (or rebuild) the Graphify knowledge graph for ``path``."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        if not await backend.is_available():
            get_console().print(await backend.install_hint())
            raise typer.Exit(code=1)

        info(f"Building graph for [accent]{to_privacy_path(backend.root)}[/accent] ...")

        # Setup Graphify credentials from active provider/store
        active_provider = setup_graphify_credentials(backend.root)

        if not active_provider:
            warn(
                "No AI provider configured.\n\n"
                "Run:\n"
                "  forge auth login\n"
                "  forge provider use <provider>\n"
                "  forge model use <model>\n\n"
                "Continuing with syntax-only indexing..."
            )
            info("Building syntax-only graph (no LLM needed)...")
            try:
                result = await backend.update_graph(force=force, no_cluster=no_cluster)
                snapshot = result.snapshot
                get_console().print(
                    f"  nodes:      [bold]{len(snapshot.nodes)}[/bold]\n"
                    f"  edges:      [bold]{len(snapshot.edges)}[/bold]\n"
                    f"  communities:[bold]{len(snapshot.communities)}[/bold]"
                )
                for label, value in result.artifacts.items():
                    get_console().print(f"  [muted]{label}:[/muted] {to_privacy_path(value)}")
                success("Syntax-only graph built successfully.")
                return
            except Exception as update_exc:
                error(f"Syntax-only graph build failed: {update_exc}")
                raise typer.Exit(code=1) from update_exc

        try:
            result = await backend.build(force=force, no_cluster=no_cluster)
            snapshot = result.snapshot
            get_console().print(
                f"  nodes:      [bold]{len(snapshot.nodes)}[/bold]\n"
                f"  edges:      [bold]{len(snapshot.edges)}[/bold]\n"
                f"  communities:[bold]{len(snapshot.communities)}[/bold]"
            )
            for label, value in result.artifacts.items():
                get_console().print(f"  [muted]{label}:[/muted] {to_privacy_path(value)}")
            success("Graph built.")
        except Exception as exc:
            exc_msg = str(exc).lower()
            is_key_issue = "api key" in exc_msg or "api_key" in exc_msg or "credentials" in exc_msg or "token" in exc_msg

            if is_key_issue:
                warn(
                    "Semantic indexing failed or was skipped because of API key issues.\n"
                    "Continuing with syntax-only indexing..."
                )
                info("Building syntax-only graph (no LLM needed)...")
                try:
                    result = await backend.update_graph(force=force, no_cluster=no_cluster)
                    snapshot = result.snapshot
                    get_console().print(
                        f"  nodes:      [bold]{len(snapshot.nodes)}[/bold]\n"
                        f"  edges:      [bold]{len(snapshot.edges)}[/bold]\n"
                        f"  communities:[bold]{len(snapshot.communities)}[/bold]"
                    )
                    for label, value in result.artifacts.items():
                        get_console().print(f"  [muted]{label}:[/muted] {to_privacy_path(value)}")
                    success("Syntax-only graph built successfully.")
                except Exception as update_exc:
                    error(f"Syntax-only graph build failed: {update_exc}")
                    raise typer.Exit(code=1) from update_exc
            else:
                error(f"Graph build failed: {exc}")
                raise typer.Exit(code=1) from exc

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"Graph build failed: {exc}")
        raise typer.Exit(code=1) from exc


__all__ = ["app"]
