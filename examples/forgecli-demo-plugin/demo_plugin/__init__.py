"""Example ForgeCLI plugin: registers a custom provider.

Install with::

    forge plugin install examples/forgecli-demo-plugin
    forge plugin enable demo
    forge plugin doctor demo

The plugin is fully self-contained: it does not import anything
private from ForgeCLI, it only uses the public
:class:`forgecli.sdk.PluginManager` API and the
:class:`forgecli.providers.base.Provider` Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Provider,
    Role,
)

# Plugin-level configuration. The SDK merges ``default_config()``
# into the persisted config under ``plugin.demo``.
_DEFAULT_CONFIG: dict[str, Any] = {
    "greeting": "hello",
    "max_tokens": 256,
}


@dataclass
class DemoConfig:
    """The merged configuration for the demo plugin."""

    greeting: str = "hello"
    max_tokens: int = 256


class DemoProvider(Provider):
    """A trivial provider that echoes the prompt as the answer.

    Useful as a starting point for plugin authors; the SDK exposes
    every method on the abstract base, so plugin authors can copy
    this class and replace the chat implementation with a real
    call to their service.
    """

    name = "demo"

    def __init__(self, config: DemoConfig | None = None) -> None:
        super().__init__(config or DemoConfig())  # type: ignore[arg-type]
        self._config = config or DemoConfig()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Echo the last user message back, prefixed with the greeting."""
        last_user = next(
            (m for m in reversed(request.messages) if m.role is Role.USER),
            None,
        )
        body = (
            f"{self._config.greeting}, "
            f"{last_user.content if last_user else 'world'}!"
        )
        return ChatResponse(
            model=request.model or "demo",
            message=ChatMessage(role=Role.ASSISTANT, content=body),
            finish_reason="stop",
            prompt_tokens=sum(len(m.content) for m in request.messages),
            completion_tokens=len(body),
        )


def register(manager: Any) -> None:
    """The entry-point called by the SDK when the plugin is enabled."""
    manager.register_provider("demo", DemoProvider)
    # Register the default config so ``forge plugin configure demo
    # greeting=hi`` works out of the box.
    state = manager.state.plugins.get("demo")
    if state is not None and not state.config:
        manager.configure("demo", **_DEFAULT_CONFIG)


def health(manager: Any) -> list[dict[str, Any]]:
    """Custom health probe reported by ``forge plugin doctor demo``."""
    issues: list[dict[str, Any]] = []
    if not manager.state.plugins.get("demo", None):
        issues.append(
            {
                "severity": "warn",
                "message": "plugin is not in the enabled set",
                "suggestion": "run: forge plugin enable demo",
            }
        )
    return issues
