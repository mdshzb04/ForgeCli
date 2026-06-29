"""In-memory registry of named prompts."""

from __future__ import annotations

from collections.abc import Iterable

from forgecli.core.service import Service


class PromptRegistry(Service):
    """Stores prompts by name without touching the filesystem."""

    name = "prompts.registry"

    def __init__(self) -> None:
        super().__init__()
        self._prompts: dict[str, str] = {}

    def register(self, name: str, template: str) -> None:
        self._prompts[name] = template

    def get(self, name: str) -> str:
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Prompt not registered: {name!r}") from exc

    def names(self) -> list[str]:
        return sorted(self._prompts)

    def items(self) -> Iterable[tuple[str, str]]:
        return self._prompts.items()
