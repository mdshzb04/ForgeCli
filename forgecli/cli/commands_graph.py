"""``forge graph`` subcommand group: build / query / explain.

These commands integrate the external Graphify CLI behind the
:mod:`forgecli.graph.repository` abstraction. When Graphify is not
installed the commands print an installation hint instead of failing.
"""

from __future__ import annotations

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
        info(f"Building graph for [accent]{backend.root}[/accent] ...")
        result = await backend.build(force=force, no_cluster=no_cluster)
        snapshot = result.snapshot
        get_console().print(
            f"  nodes:      [bold]{len(snapshot.nodes)}[/bold]\n"
            f"  edges:      [bold]{len(snapshot.edges)}[/bold]\n"
            f"  communities:[bold]{len(snapshot.communities)}[/bold]"
        )
        for label, value in result.artifacts.items():
            get_console().print(f"  [muted]{label}:[/muted] {value}")
        success("Graph built.")

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except Exception as exc:
        error(f"Graph build failed: {exc}")
        raise typer.Exit(code=1) from exc


@app.command("query")
def query_cmd(
    question: str = typer.Argument(..., help="Free-form question to ask the graph."),
    path: str = typer.Option(".", "--path", "-p", help="Project root containing graph.json."),
    budget: int = typer.Option(2000, "--budget", help="Output token budget."),
    dfs: bool = typer.Option(False, "--dfs", help="Use depth-first traversal."),
    cited_only: bool = typer.Option(
        False, "--cited-only", help="Print only the cited nodes after the answer."
    ),
) -> None:
    """Ask a free-form question; Graphify BFS/DFS-traverses the graph."""
    import asyncio

    backend = _build_backend(Path(path))

    async def _run() -> None:
        if not await backend.is_available():
            get_console().print(await backend.install_hint())
            raise typer.Exit(code=1)
        result = await backend.query(question, budget=budget)
        get_console().print(result.answer)
        if cited_only and result.cited_nodes:
            get_console().print()
            get_console().print("[muted]Cited nodes:[/muted]")
            for cited in result.cited_nodes:
                get_console().print(f"  • {cited}")

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
                get_console().print(
                    f"  • {node.label}"
                    + (f"  [muted]({node.source_file})[/muted]" if node.source_file else "")
                )

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
            ["Project root", str(backend.root)],
            ["Graphify installed", "yes" if installed else "no"],
            ["Graphify version", version],
            ["graph.json", str(backend.artifacts.graph_json)],
            ["graph.json exists", "yes" if graph_exists else "no"],
        ]
        table(["Field", "Value"], rows, title="Graphify status")

    asyncio.run(_run())


__all__ = ["app"]
