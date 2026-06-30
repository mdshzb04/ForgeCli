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

        # Check if any LLM API key is configured
        has_api_key = any(
            os.environ.get(k) for k in [
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "GOOGLE_API_KEY",
                "GEMINI_API_KEY",
                "GROQ_API_KEY",
                "MISTRAL_API_KEY",
                "OPENROUTER_API_KEY",
            ]
        )

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
            is_key_issue = "api key" in exc_msg or "api_key" in exc_msg or "credentials" in exc_msg or "token" in exc_msg or not has_api_key

            if is_key_issue:
                warn(
                    "Semantic indexing failed or was skipped because no LLM API key is configured.\n"
                    "Graphify requires an LLM API key for full semantic indexing (extracting inferred relationships).\n"
                    "To enable semantic indexing, set one of the following environment variables:\n"
                    "  - export GEMINI_API_KEY='your-key'\n"
                    "  - export OPENAI_API_KEY='your-key'\n"
                    "  - export ANTHROPIC_API_KEY='your-key'\n"
                    "Falling back gracefully to syntax-only indexing (AST parsing)..."
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
