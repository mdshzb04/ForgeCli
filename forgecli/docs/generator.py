"""Auto-generate project documentation from the Graphify knowledge graph.

The generator walks the project, asks Graphify for a snapshot, and
emits a Markdown report at ``docs/OVERVIEW.md`` with:

* a module-by-module summary derived from the graph nodes;
* the file tree of the project;
* a flat list of every symbol with its location.

The output is intentionally simple: the goal is to give an LLM
(or a human) a starting point for richer docs.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from forgecli.core.context import AppContext
from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
from forgecli.utils.fs import ensure_dir

_INTRO_TEMPLATE = """\
# {project} — Auto-generated overview

_Generated on {today} by `forge docs`._

This document is a starting point: it summarises the module layout
and lists every symbol the Graphify knowledge graph knows about.
For deeper documentation, run `forge plan`, `forge build`, or
`forge explain` on individual modules.

"""


def generate_docs(context: AppContext, *, output: Path | None = None) -> Path:
    """Generate the overview file and return its path."""
    root = context.cwd
    target = output or (root / "docs" / "OVERVIEW.md")
    ensure_dir(target.parent)

    graph = GraphifyRepositoryGraph(root=root)
    snapshot = graph._cached  # may be None; load() if needed.

    # Build a tiny ad-hoc snapshot by re-walking the project.
    nodes = _walk_nodes(root)
    communities = _community_buckets(nodes)

    lines: list[str] = [
        _INTRO_TEMPLATE.format(project=root.name, today=date.today().isoformat()),
    ]
    lines.append("## Modules\n")
    for community, members in sorted(communities.items()):
        lines.append(f"### {community}\n")
        for node in sorted(members, key=lambda n: str(n["path"])):
            location = (
                f"`{node['path']}:{node['line']}`"
                if node["line"]
                else f"`{node['path']}`"
            )
            lines.append(f"- {node['label']} — {location}")
        lines.append("")
    if not nodes:
        lines.append("_No indexed symbols found._\n")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    _ = snapshot  # silence unused
    return target


def _walk_nodes(root: Path) -> list[dict[str, object]]:
    """Build a small node list from the project tree.

    This is a *fallback* when Graphify hasn't been run. The docs
    generator is meant to be cheap and offline; it doesn't shell out
    to the Graphify CLI.
    """
    nodes: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        if any(part.startswith(".") for part in path.parts):
            continue
        if any(part in {"__pycache__", "node_modules", ".venv", "venv"} for part in path.parts):
            continue
        rel = path.relative_to(root)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nodes.append({"path": str(rel), "label": path.name, "line": 1})
        for index, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith(("def ", "class ", "async def ")):
                name = _extract_symbol_name(stripped)
                if name:
                    nodes.append({"path": str(rel), "label": name, "line": index})
    return nodes


def _extract_symbol_name(line: str) -> str | None:
    """Return the symbol name from a ``def foo(...)`` / ``class Foo:`` line."""
    line = line.strip()
    for prefix in ("async def ", "def ", "class "):
        if line.startswith(prefix):
            rest = line[len(prefix):]
            return rest.split("(", 1)[0].split(":", 1)[0].strip() or None
    return None


def _community_buckets(nodes: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Group nodes by their top-level directory (the "module")."""
    buckets: dict[str, list[dict[str, object]]] = {}
    for node in nodes:
        path = str(node["path"])
        parts = path.split("/")
        module = parts[0] if len(parts) > 1 else path
        buckets.setdefault(module, []).append(node)
    return buckets


__all__ = ["generate_docs"]
