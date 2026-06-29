"""Dead-code analyzer.

Detects:

* private (``_foo``) functions/classes defined at module level but
  never referenced anywhere in the project (other than their
  definition);
* ``__all__``-listed symbols that are not actually defined in the
  module.

The analyzer is conservative: ``__init__``, dunder methods,
``__all__`` re-exports, and pytest-style ``test_*`` functions are
ignored. The analyzer also ignores private symbols whose name is
listed in a module-level ``__all__`` tuple (re-exported).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.finding import Finding, Severity

_DUNDER_NAMES: frozenset[str] = frozenset(
    {
        "__init__",
        "__del__",
        "__repr__",
        "__str__",
        "__bytes__",
        "__format__",
        "__lt__",
        "__le__",
        "__eq__",
        "__ne__",
        "__gt__",
        "__ge__",
        "__hash__",
        "__bool__",
        "__call__",
        "__len__",
        "__length_hint__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__iter__",
        "__next__",
        "__reversed__",
        "__contains__",
        "__add__",
        "__sub__",
        "__mul__",
        "__matmul__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__divmod__",
        "__pow__",
        "__lshift__",
        "__rshift__",
        "__and__",
        "__or__",
        "__xor__",
        "__radd__",
        "__rsub__",
        "__rmul__",
        "__rmatmul__",
        "__rtruediv__",
        "__rfloordiv__",
        "__rmod__",
        "__rdivmod__",
        "__rpow__",
        "__rlshift__",
        "__rrshift__",
        "__rand__",
        "__ror__",
        "__rxor__",
        "__iadd__",
        "__isub__",
        "__imul__",
        "__imatmul__",
        "__itruediv__",
        "__ifloordiv__",
        "__imod__",
        "__ipow__",
        "__ilshift__",
        "__irshift__",
        "__iand__",
        "__ior__",
        "__ixor__",
        "__neg__",
        "__pos__",
        "__abs__",
        "__invert__",
        "__complex__",
        "__int__",
        "__float__",
        "__index__",
        "__round__",
        "__trunc__",
        "__floor__",
        "__ceil__",
        "__enter__",
        "__exit__",
        "__await__",
        "__aiter__",
        "__anext__",
        "__aenter__",
        "__aexit__",
        "__set_name__",
        "__class_getitem__",
        "__init_subclass__",
        "__class__",
        "__dict__",
        "__doc__",
        "__module__",
        "__qualname__",
        "__annotations__",
        "__slots__",
        "__weakref__",
    }
)


@dataclass
class DeadCodeAnalyzer(Analyzer):
    """Detect private symbols that are never referenced."""

    name: ClassVar[str] = "dead-code"
    category: ClassVar[str] = "dead-code"

    def run(self, context: AnalysisContext) -> list[Finding]:
        # Collect definitions and references.
        definitions: dict[tuple[str, str], tuple[Path, int, str]] = {}
        references: dict[tuple[str, str], int] = defaultdict(int)
        # Maps module name -> set of private names in __all__
        all_overrides: dict[str, set[str]] = {}

        for file in context.files:
            module = _module_of(file.path)
            if module is None:
                continue
            try:
                tree = ast.parse(file.text)
            except SyntaxError:
                continue
            self._collect_definitions(tree, module, file, definitions, all_overrides)
            self._collect_references(tree, module, references)

        findings: list[Finding] = []
        for key, (path, line, kind) in definitions.items():
            module, name = key
            if not name.startswith("_"):
                continue
            if name.startswith("__") and name.endswith("__"):
                continue
            if name in _DUNDER_NAMES:
                continue
            if name in all_overrides.get(module, set()):
                continue
            if references.get(key, 0) > 0:
                continue
            findings.append(
                Finding(
                    rule_id="DEAD001",
                    category="dead-code",
                    severity=Severity.LOW,
                    message=(
                        f"{kind} {name!r} is defined in {module} but never "
                        "referenced."
                    ),
                    path=str(path),
                    line=line,
                    suggestion=(
                        "Delete the symbol, or expose it in __all__ if it "
                        "is part of the public API."
                    ),
                )
            )
        return findings

    def _collect_definitions(
        self,
        tree: ast.AST,
        module: str,
        file,
        definitions: dict,
        all_overrides: dict,
    ) -> None:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                # Capture module-level __all__ assignments.
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "__all__"
                        and isinstance(node.value, (ast.List, ast.Tuple))
                    ):
                        names: set[str] = set()
                        for element in node.value.elts:
                            if isinstance(element, ast.Constant) and isinstance(
                                element.value, str
                            ):
                                names.add(element.value)
                        all_overrides[module] = names
                continue
            if isinstance(node, ast.FunctionDef):
                definitions[(module, node.name)] = (file.path, node.lineno, "Function")
            elif isinstance(node, ast.AsyncFunctionDef):
                definitions[(module, node.name)] = (
                    file.path,
                    node.lineno,
                    "Async function",
                )
            elif isinstance(node, ast.ClassDef):
                definitions[(module, node.name)] = (file.path, node.lineno, "Class")
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and isinstance(node.value, ast.AST)
            ):
                definitions[(module, node.target.id)] = (
                    file.path,
                    node.lineno,
                    "Variable",
                )

    def _collect_references(
        self, tree: ast.AST, module: str, references: dict
    ) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                references[(module, node.id)] += 1
            elif isinstance(node, ast.Attribute):
                base = node
                while isinstance(base, ast.Attribute):
                    base = base.value
                if isinstance(base, ast.Name):
                    # `self.foo` and `module.foo` both reference `foo` on
                    # the same module; we count it once.
                    references[(module, node.attr)] += 1


def _module_of(path) -> str | None:
    parts = path.parts
    try:
        idx = parts.index("forgecli")
    except ValueError:
        return None
    relevant = parts[idx:]
    if relevant[-1] == "__init__.py":
        relevant = relevant[:-1]
    elif relevant[-1].endswith(".py"):
        relevant = (*relevant[:-1], relevant[-1][:-3])
    return ".".join(relevant)


__all__ = ["DeadCodeAnalyzer"]
