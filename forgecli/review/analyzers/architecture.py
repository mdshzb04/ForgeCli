"""Architecture analyzer.

Two heuristics:

* **Layering**: enforce a "lower layers cannot import higher layers"
  rule. By default we use the top-level ``forgecli`` package layout
  (core -> utils -> providers -> graph -> optimizer -> builder ->
  review) and forbid e.g. ``core`` from importing ``graph``. Users can
  override the layer ordering via the ``layers`` attribute.
* **Forbidden imports**: flag any import from a configurable
  blacklist (default empty). The analyzer is conservative: it never
  blocks legitimate patterns.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from typing import ClassVar

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.finding import Finding, Severity

_DEFAULT_LAYERS: tuple[str, ...] = (
    "core",
    "config",
    "utils",
    "providers",
    "graph",
    "optimizer",
    "builder",
    "review",
    "planner",
    "git",
    "memory",
    "prompts",
    "templates",
    "cli",
    "commit",
    "build",
)


@dataclass
class ArchitectureAnalyzer(Analyzer):
    """Enforce a layer ordering and detect circular imports."""

    name: ClassVar[str] = "architecture"
    category: ClassVar[str] = "architecture"
    layers: tuple[str, ...] = _DEFAULT_LAYERS
    forbidden_imports: tuple[str, ...] = ()

    def run(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._scan_layering(context))
        findings.extend(self._scan_circular_imports(context))
        findings.extend(self._scan_forbidden_imports(context))
        return findings

    # ------------------------------------------------------------------
    # Layering
    # ------------------------------------------------------------------

    def _scan_layering(self, context: AnalysisContext) -> list[Finding]:
        out: list[Finding] = []
        layer_index = {layer: index for index, layer in enumerate(self.layers)}
        for file in context.files:
            try:
                tree = ast.parse(file.text)
            except SyntaxError:
                continue
            file_layer = _top_level_layer(file.path)
            if file_layer is None or file_layer not in layer_index:
                continue
            for node in ast.walk(tree):
                imported = _imported_module(node)
                if imported is None:
                    continue
                target_layer = _layer_of(imported, layer_index)
                if target_layer is None:
                    continue
                if layer_index[target_layer] <= layer_index[file_layer]:
                    continue
                out.append(
                    Finding(
                        rule_id="ARCH001",
                        category="architecture",
                        severity=Severity.MEDIUM,
                        message=(
                            f"Layer '{file_layer}' imports from higher layer "
                            f"'{target_layer}' ({imported})."
                        ),
                        path=str(file.path),
                        line=getattr(node, "lineno", 1),
                        suggestion=(
                            "Move the dependency, or invert the call so the "
                            "lower layer exposes a callback."
                        ),
                    )
                )
        return out

    def _scan_circular_imports(self, context: AnalysisContext) -> list[Finding]:
        """Detect cycles in the package-level import graph.

        For each ``forgecli/<layer>/...`` file we record the set of
        other layers it imports. A cycle is reported as a single
        finding describing the cycle.
        """
        graph: dict[str, set[str]] = defaultdict(set)
        for file in context.files:
            layer = _top_level_layer(file.path)
            if layer is None or layer not in self.layers:
                continue
            try:
                tree = ast.parse(file.text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                imported = _imported_module(node)
                if imported is None:
                    continue
                target = _layer_of(imported, {layer: idx for idx, layer in enumerate(self.layers)})
                if target is None or target == layer:
                    continue
                graph[layer].add(target)
        out: list[Finding] = []
        for cycle in _find_cycles(graph):
            message = " -> ".join([*cycle, cycle[0]])
            out.append(
                Finding(
                    rule_id="ARCH002",
                    category="architecture",
                    severity=Severity.MEDIUM,
                    message=f"Circular import between layers: {message}",
                    path=None,
                    line=None,
                    suggestion=(
                        "Break the cycle by extracting a shared interface "
                        "or by deferring the import inside the function."
                    ),
                    extra={"cycle": cycle},
                )
            )
        return out

    def _scan_forbidden_imports(self, context: AnalysisContext) -> list[Finding]:
        if not self.forbidden_imports:
            return []
        out: list[Finding] = []
        for file in context.files:
            try:
                tree = ast.parse(file.text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                imported = _imported_module(node)
                if imported is None:
                    continue
                for forbidden in self.forbidden_imports:
                    if imported == forbidden or imported.startswith(forbidden + "."):
                        out.append(
                            Finding(
                                rule_id="ARCH003",
                                category="architecture",
                                severity=Severity.HIGH,
                                message=(
                                    f"Forbidden import: '{imported}' is not "
                                    f"allowed in this project."
                                ),
                                path=str(file.path),
                                line=getattr(node, "lineno", 1),
                                suggestion=(
                                    "Use the public API exposed by the "
                                    "intended module."
                                ),
                            )
                        )
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _top_level_layer(path) -> str | None:
    """Return the layer name for a path under the project source root."""
    parts = path.parts
    # Look for "forgecli" in the path; the next part is the layer.
    try:
        idx = parts.index("forgecli")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    return parts[idx + 1]


def _imported_module(node: ast.AST) -> str | None:
    """Return the dotted module name for an import node, or None."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            return alias.name
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            return None
        return node.module
    return None


def _layer_of(module: str, layer_index: dict[str, int]) -> str | None:
    """Return the layer name for a dotted module, or None."""
    if not module:
        return None
    parts = module.split(".")
    if "forgecli" in parts:
        idx = parts.index("forgecli")
        if idx + 1 < len(parts):
            candidate = parts[idx + 1]
            if candidate in layer_index:
                return candidate
    # External modules: not a layer.
    return None


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return a list of cycles in ``graph`` (each cycle as a list of nodes)."""
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()
    for start in graph:
        visited: set[str] = set()

        def dfs(node: str, stack: list[str], visited: set[str]) -> None:
            if node in visited:
                if node in stack:
                    cycle_start = stack.index(node)
                    cycle = stack[cycle_start:]
                    key = tuple(sorted(cycle))
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cycle)
                return
            visited.add(node)
            stack.append(node)
            for neighbor in graph.get(node, ()):
                dfs(neighbor, stack, visited)
            stack.pop()

        dfs(start, [], visited)
    return cycles


__all__ = ["ArchitectureAnalyzer"]


# Silence unused-import warnings.
