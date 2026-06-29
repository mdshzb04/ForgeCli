"""Complexity analyzer.

Reports per-function:

* **line count** — anything over a threshold (default 80) is flagged;
* **parameter count** — anything over 5 is flagged;
* **cyclomatic complexity** — branches + boolean operators + 1.

The numbers are intentionally conservative; this is a smoke-detector
for "this function has gotten too big" rather than a precise metric.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import ClassVar

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.finding import Finding, Severity

_BRANCH_NODES: tuple[type[ast.AST], ...] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
    ast.Match,
)


@dataclass
class ComplexityAnalyzer(Analyzer):
    """Cyclomatic-ish complexity and size metrics per function."""

    name: ClassVar[str] = "complexity"
    category: ClassVar[str] = "complexity"
    max_function_lines: int = 80
    max_parameters: int = 5
    max_cyclomatic: int = 12

    def run(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        parents: dict[ast.AST, ast.AST] = {}
        for file in context.files:
            try:
                tree = ast.parse(file.text)
            except SyntaxError:
                continue
            _link_parents(tree, parents)
            for function in _walk_functions(tree):
                findings.extend(self._check_function(file, function, parents))
        return findings

    def _check_function(self, file, function, parents) -> list[Finding]:
        out: list[Finding] = []
        line_count = _function_length(function)
        params = len(function.args.args) + len(function.args.kwonlyargs)
        cyclomatic = _cyclomatic_complexity(function)
        name = _qualified_function_name(function, parents)

        if line_count > self.max_function_lines:
            out.append(
                Finding(
                    rule_id="CPLX001",
                    category="complexity",
                    severity=Severity.LOW,
                    message=(
                        f"Function {name} is {line_count} lines long "
                        f"(>{self.max_function_lines})."
                    ),
                    path=str(file.path),
                    line=function.lineno,
                    suggestion="Split into smaller helpers; extract branches.",
                    extra={"lines": line_count},
                )
            )
        if params > self.max_parameters:
            out.append(
                Finding(
                    rule_id="CPLX002",
                    category="complexity",
                    severity=Severity.LOW,
                    message=(
                        f"Function {name} takes {params} parameters "
                        f"(>{self.max_parameters}); consider a parameter object."
                    ),
                    path=str(file.path),
                    line=function.lineno,
                    suggestion="Bundle related parameters into a dataclass.",
                    extra={"params": params},
                )
            )
        if cyclomatic > self.max_cyclomatic:
            out.append(
                Finding(
                    rule_id="CPLX003",
                    category="complexity",
                    severity=Severity.MEDIUM,
                    message=(
                        f"Function {name} has cyclomatic complexity "
                        f"{cyclomatic} (>{self.max_cyclomatic})."
                    ),
                    path=str(file.path),
                    line=function.lineno,
                    suggestion=(
                        "Decompose the function along its decision points."
                    ),
                    extra={"cyclomatic": cyclomatic},
                )
            )
        return out


def _walk_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _link_parents(root: ast.AST, parents: dict[ast.AST, ast.AST]) -> None:
    """Populate ``parents[child] = parent`` for every AST node in ``root``."""
    for parent in ast.walk(root):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent


def _function_length(function) -> int:
    if function.end_lineno is None or function.lineno is None:
        return 0
    return function.end_lineno - function.lineno + 1


def _cyclomatic_complexity(function) -> int:
    """Approximate cyclomatic complexity: 1 + number of decision points."""
    complexity = 1
    for node in ast.walk(function):
        if isinstance(node, _BRANCH_NODES):
            complexity += 1
        if isinstance(node, ast.BoolOp):
            # Each `and`/`or` operator adds an extra edge.
            complexity += len(node.values) - 1
        if isinstance(node, ast.comprehension):
            # Comprehensions have implicit branches.
            complexity += sum(1 for _ in node.ifs)
        if isinstance(node, ast.ExceptHandler):
            complexity += 1
    return complexity


def _qualified_function_name(function, parents) -> str:
    """Best-effort qualified name for a function definition."""
    parts: list[str] = [function.name]
    parent = parents.get(function)
    while isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        parts.append(parent.name)
        parent = parents.get(parent)
    return ".".join(reversed(parts))


__all__ = ["ComplexityAnalyzer"]
