"""Node and edge value types for the code graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeKind(str, Enum):
    """The kind of entity represented by a graph node."""

    FILE = "file"
    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    SYMBOL = "symbol"


class EdgeKind(str, Enum):
    """The kind of relationship represented by a graph edge."""

    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    REFERENCES = "references"
    DEFINED_IN = "defined_in"
    OVERRIDES = "overrides"


@dataclass(frozen=True)
class Node:
    """A node in the code graph."""

    id: str
    kind: NodeKind
    name: str
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
