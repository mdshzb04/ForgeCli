"""Live runtime state for the model router.

The active provider selection (claude / openai / gemini / auto) is
persisted to ``data_dir/router.json`` and surfaced on every
:class:`AppContext` via ``extras``. A selection of ``"auto"`` triggers
the cheapest-compatible algorithm on every chat call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from forgecli.providers.router import ModelCapabilities, RouteDecision, SelectionMode


@dataclass
class RouterState:
    """The user-chosen provider/model selection."""

    choice: str = "auto"
    model: str | None = None
    provider: str | None = None

    @classmethod
    def from_extras(cls, extras: dict[str, object]) -> RouterState:
        state = cls()
        choice = extras.get("router.choice") or extras.get("router_choice")
        if isinstance(choice, str):
            state.choice = choice
        model = extras.get("router.model") or extras.get("router_model")
        if isinstance(model, str):
            state.model = model
        provider = extras.get("router.provider") or extras.get("router_provider")
        if isinstance(provider, str):
            state.provider = provider
        return state

    def to_extras(self) -> dict[str, str]:
        out: dict[str, str] = {"router.choice": self.choice}
        if self.model:
            out["router.model"] = self.model
        if self.provider:
            out["router.provider"] = self.provider
        return out


def load_state(path: Path) -> RouterState:
    if not path.exists():
        return RouterState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RouterState()
    state = RouterState()
    choice = payload.get("choice")
    if isinstance(choice, str):
        state.choice = choice
    model = payload.get("model")
    if isinstance(model, str):
        state.model = model
    provider = payload.get("provider")
    if isinstance(provider, str):
        state.provider = provider
    return state


def save_state(path: Path, state: RouterState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"choice": state.choice, "model": state.model, "provider": state.provider},
            indent=2,
        ),
        encoding="utf-8",
    )


__all__ = [
    "ModelCapabilities",
    "RouteDecision",
    "RouterState",
    "SelectionMode",
    "load_state",
    "save_state",
]
