"""In-memory registry of named templates."""

from __future__ import annotations

from collections.abc import Iterable

from forgecli.core.service import Service


class TemplateRegistry(Service):
    """Stores named templates; higher-level loaders can hydrate it from disk."""

    name = "templates.registry"

    def __init__(self) -> None:
        super().__init__()
        self._templates: dict[str, str] = {}

    def register(self, name: str, template: str) -> None:
        self._templates[name] = template

    def get(self, name: str) -> str:
        try:
            return self._templates[name]
        except KeyError as exc:
            raise KeyError(f"Template not registered: {name!r}") from exc

    def names(self) -> list[str]:
        return sorted(self._templates)

    def items(self) -> Iterable[tuple[str, str]]:
        return self._templates.items()
