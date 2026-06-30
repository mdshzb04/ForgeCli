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
    table,
    warn,
)
from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
from forgecli.graph.repository import GraphEdge
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


@app.command("query")
def query_cmd(
    question: str = typer.Argument(..., help="Query term to search/traverse the graph for."),
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
    budget: int = typer.Option(2000, "--budget", help="Output token budget."),
    dfs: bool = typer.Option(False, "--dfs", help="Use depth-first traversal."),
    cited_only: bool = typer.Option(
        False, "--cited-only", help="Print only the cited nodes after the traversal results."
    ),
) -> None:
    """Traverse the graph using BFS/DFS to return matching nodes."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        if not await backend.is_available():
            get_console().print(await backend.install_hint())
            raise typer.Exit(code=1)
        result = await backend.query(question, budget=budget)
        
        # Count nodes and edges in the response
        lines = result.answer.splitlines()
        node_count = sum(1 for line in lines if line.strip().startswith("NODE "))
        edge_count = sum(1 for line in lines if line.strip().startswith("EDGE "))
        
        get_console().print(f"[bold cyan]Graph traversal results for query '{question}':[/bold cyan]")
        get_console().print(f"[muted]Traversed {node_count} nodes and {edge_count} edges.[/muted]\n")
        get_console().print(result.answer)
        if cited_only and result.cited_nodes:
            get_console().print()
            get_console().print("[muted]Cited nodes:[/muted]")
            for cited in result.cited_nodes:
                get_console().print(f"  • {to_privacy_path(cited)}")

        # When no nodes are found, suggest similar commands or rebuilding the graph
        if not result.cited_nodes:
            try:
                snapshot = await backend.load()
                query_lower = question.lower()
                matches = [
                    node.label for node in snapshot.nodes
                    if query_lower in node.label.lower() or any(part in node.label.lower() for part in query_lower.split())
                ][:5]
            except Exception:
                matches = []

            get_console().print()
            warn("No matching nodes were found in the repository graph for your query.")
            if matches:
                info(f"Did you mean one of these nodes? {', '.join(f'[accent]{m}[/accent]' for m in matches)}")
            else:
                info(
                    "Suggestions:\n"
                    "  • Try using different keywords related to your functions, classes, or files (e.g. 'auth', 'build_cmd').\n"
                    "  • Ensure the graph is up to date by rebuilding it: [bold cyan]forge graph build --force[/bold cyan]\n"
                    "  • Use [bold cyan]forge graph status[/bold cyan] to verify the index exists."
                )

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"Graph query failed: {exc}")
        raise typer.Exit(code=1) from exc


@app.command("explain")
def explain_cmd(
    target: str = typer.Argument(..., help="Node label, id, or filename to explain."),
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
) -> None:
    """Plain-language explanation of ``target`` and its neighbors."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        if not await backend.is_available():
            get_console().print(await backend.install_hint())
            raise typer.Exit(code=1)
        result = await backend.explain(target)
        get_console().print(result.explanation)
        if result.related:
            get_console().print()
            get_console().print("[muted]Related nodes:[/muted]")
            for node in result.related:
                source_file_part = f"  [muted]({to_privacy_path(node.source_file)})[/muted]" if node.source_file else ""
                get_console().print(f"  • {node.label}{source_file_part}")

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"Graph explain failed: {exc}")
        raise typer.Exit(code=1) from exc


@app.command("path")
def path_cmd(
    a: str = typer.Argument(..., help="Source node label or id."),
    b: str = typer.Argument(..., help="Target node label or id."),
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
) -> None:
    """Print the shortest edge path between two nodes (in-memory BFS)."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        if not await backend.is_available():
            get_console().print(await backend.install_hint())
            raise typer.Exit(code=1)
        edges = await backend.shortest_path(a, b)
        if not edges:
            warn(f"No path between {a!r} and {b!r}.")
            return
        rows = [[edge.source, edge.relation, edge.target] for edge in edges]
        table(["Source", "Relation", "Target"], rows, title=f"{a} → {b}")

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"Graph path failed: {exc}")
        raise typer.Exit(code=1) from exc


@app.command("affected")
def affected_cmd(
    target: str = typer.Argument(..., help="Node label or id whose blast radius to compute."),
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
    relation: list[str] | None = typer.Option(
        None, "--relation", help="Edge relation to traverse (repeatable)."
    ),
    depth: int = typer.Option(2, "--depth", help="Reverse traversal depth."),
) -> None:
    """List edges/nodes that are impacted by changes to ``target``."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        if not await backend.is_available():
            get_console().print(await backend.install_hint())
            raise typer.Exit(code=1)
        edges: list[GraphEdge] = await backend.affected(
            target, relation=relation, depth=depth
        )
        if not edges:
            warn(f"No reverse-traversal edges found for {target!r}.")
            return
        rows = [[edge.source, edge.relation, edge.target] for edge in edges]
        table(
            ["Source", "Relation", "Target"],
            rows,
            title=f"Blast radius of {target} (depth={depth})",
        )

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"Graph affected failed: {exc}")
        raise typer.Exit(code=1) from exc


@app.command("status")
def status_cmd(
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
) -> None:
    """Show whether Graphify is installed and whether graph.json exists."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        installed = await backend.is_available()
        version = await backend.client.version() if installed else "(not installed)"
        graph_exists = backend.artifacts.graph_json.exists()
        rows = [
            ["Backend", backend.name],
            ["Project root", to_privacy_path(backend.root)],
            ["Graphify installed", "yes" if installed else "no"],
            ["Graphify version", version],
            ["graph.json", to_privacy_path(backend.artifacts.graph_json)],
            ["graph.json exists", "yes" if graph_exists else "no"],
        ]
        table(["Field", "Value"], rows, title="Graphify status")

    asyncio.run(_run())


@app.command("open")
def open_cmd(
    path: str = typer.Option(".", "--path", "-p", help="Project root containing the interactive graph HTML."),
) -> None:
    """Launch the interactive graph visualization in the default web browser."""
    import webbrowser

    html_path = Path(path).resolve() / "graphify-out" / "graph.html"
    if not html_path.exists():
        error(
            f"No interactive graph visualization found at {to_privacy_path(html_path)}.\n"
            "Please build the graph first using `forge graph build`."
        )
        raise typer.Exit(code=1)

    info(f"Opening interactive graph: {to_privacy_path(html_path)} ...")
    try:
        webbrowser.open(html_path.as_uri())
        success("Interactive graph launched.")
    except Exception as exc:
        error(f"Failed to open interactive graph: {exc}")
        raise typer.Exit(code=1) from exc


__all__ = ["app"]
