"""Discover prompt templates on disk."""

from __future__ import annotations

from pathlib import Path

from forgecli.core.service import Service


class PromptLoader(Service):
    """Load prompt templates by name from a base directory."""

    name = "prompts.loader"

    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self._base_dir = Path(base_dir)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def load(self, name: str) -> str:
        """Return the contents of the prompt file identified by ``name``."""
        path = self._base_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        return path.read_text(encoding="utf-8")
