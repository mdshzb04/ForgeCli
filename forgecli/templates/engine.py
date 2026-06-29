"""Render reusable project/workflow templates."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from forgecli.core.service import Service
from forgecli.utils.fs import atomic_write


class TemplateEngine(Service):
    """Render template strings and materialize them to disk."""

    name = "templates.engine"

    def __init__(self, *, renderer=None) -> None:
        super().__init__()
        # Lazy import to keep the templates module usable in tests.
        from forgecli.prompts.renderer import PromptRenderer

        self._renderer = renderer or PromptRenderer()

    def render(self, template: str, **variables: object) -> str:
        """Render ``template`` with ``variables`` using the prompt renderer."""
        return self._renderer.render(template, **variables)

    def materialize(
        self,
        target: Path,
        template: str,
        *,
        variables: Mapping[str, object] | None = None,
    ) -> Path:
        """Render ``template`` and atomically write it to ``target``."""
        content = self.render(template, **(dict(variables) if variables else {}))
        return atomic_write(target, content)
