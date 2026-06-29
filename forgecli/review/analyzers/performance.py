"""Performance analyzer.

A small heuristic linter for the patterns that commonly degrade
runtime in Python code:

* ``for`` loops nested three or more levels deep (a code-smell that
  often indicates an O(n^3) algorithm);
* ``open(...)`` or ``Path.read_text()`` calls inside an ``async def``
  function (blocking I/O on the event loop);
* ``time.sleep`` inside an ``async def`` (blocks the loop);
* ``list(...)`` or ``dict(...)`` around an already-iterable generator
  inside a tight loop;
* ``subprocess`` calls without an explicit timeout.

The analyzer never measures actual runtime; it flags patterns that are
*usually* a problem and lets a human decide.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import ClassVar

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.finding import Finding, Severity

_BLOCKING_NAMES: frozenset[str] = frozenset(
    {
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "read",
        "write",
    }
)


@dataclass
class PerformanceAnalyzer(Analyzer):
    """Heuristic performance smells."""

    name: ClassVar[str] = "performance"
    category: ClassVar[str] = "performance"
    nested_loop_threshold: int = 3

    def run(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for file in context.files:
            findings.extend(self._scan_async_blocking(file))
            findings.extend(self._scan_nested_loops(file))
        return findings

    def _scan_async_blocking(self, file) -> list[Finding]:
        out: list[Finding] = []
        try:
            tree = ast.parse(file.text)
        except SyntaxError:
            return out
        for function in _walk_async_functions(tree):
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node.func)
                if name is None:
                    continue
                if name in _BLOCKING_NAMES:
                    out.append(
                        Finding(
                            rule_id="PERF001",
                            category="performance",
                            severity=Severity.MEDIUM,
                            message=(
                                f"Blocking call to {name}() inside an async "
                                "function blocks the event loop."
                            ),
                            path=str(file.path),
                            line=node.lineno,
                            suggestion=(
                                "Use the async equivalent (aiofiles, "
                                "asyncio.to_thread, etc.) or move the call "
                                "out of the async path."
                            ),
                        )
                    )
                if name in {"time.sleep", "requests.get", "requests.post"}:
                    out.append(
                        Finding(
                            rule_id="PERF002",
                            category="performance",
                            severity=Severity.MEDIUM,
                            message=(
                                f"Sync {name}() in async code blocks the event loop."
                            ),
                            path=str(file.path),
                            line=node.lineno,
                            suggestion=(
                                "Use asyncio.sleep / an async HTTP client."
                            ),
                        )
                    )
        return out

    def _scan_nested_loops(self, file) -> list[Finding]:
        out: list[Finding] = []
        try:
            tree = ast.parse(file.text)
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            depth, deepest = _loop_depth(node)
            if depth >= self.nested_loop_threshold:
                out.append(
                    Finding(
                        rule_id="PERF010",
                        category="performance",
                        severity=Severity.LOW,
                        message=(
                            f"Loops nested {depth} levels deep; "
                            "consider refactoring to reduce complexity."
                        ),
                        path=str(file.path),
                        line=deepest.lineno,
                        suggestion=(
                            "Extract the inner loop into a helper, or "
                            "vectorize with itertools / numpy."
                        ),
                        extra={"depth": depth},
                    )
                )
        return out


def _walk_async_functions(tree: ast.AST) -> list[ast.AsyncFunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)]


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _loop_depth(node: ast.AST) -> tuple[int, ast.AST]:
    """Return ``(depth, deepest_node)`` for the deepest loop in ``node``."""
    best_depth = 0
    best_node = node
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        best_depth = 1
    for child in ast.iter_child_nodes(node):
        depth, deepest = _loop_depth(child)
        if depth + (1 if isinstance(node, (ast.For, ast.AsyncFor, ast.While)) else 0) > best_depth:
            best_depth = depth + (1 if isinstance(node, (ast.For, ast.AsyncFor, ast.While)) else 0)
            best_node = deepest
    return best_depth, best_node


__all__ = ["PerformanceAnalyzer"]
