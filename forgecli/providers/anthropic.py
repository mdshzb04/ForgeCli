"""Anthropic Messages API provider.

Targets the public ``https://api.anthropic.com/v1`` endpoint. The
provider uses ``x-api-key`` + ``anthropic-version`` headers per the
official API, and translates ChatRequest/Response into the Anthropic
``messages`` schema (system extracted from the message list).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    Role,
)
from forgecli.providers.http_base import HTTPChatProvider


@dataclass
class AnthropicConfig:
    """Configuration for the Anthropic provider."""

    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: str = "https://api.anthropic.com"
    default_model: str = "claude-3-5-haiku-latest"
    max_tokens: int = 4096
    temperature: float = 0.2
    api_version: str = "2023-06-01"


class AnthropicProvider(HTTPChatProvider):
    """Anthropic Messages API."""

    name = "anthropic"

    def __init__(
        self,
        config: AnthropicConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or AnthropicConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.anthropic.com"

    def _chat_url(self) -> str:
        return f"{self._base_url}/v1/messages"

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self.config.api_version,
        }

    def _format_request(self, request: ChatRequest) -> dict[str, Any]:
        system_parts: list[str] = []
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role is Role.SYSTEM:
                if message.content:
                    system_parts.append(message.content)
                continue
            messages.append(
                {
                    "role": message.role.value,
                    "content": message.content,
                }
            )
        body: dict[str, Any] = {
            "model": request.model or self.config.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens or self.config.max_tokens,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        body["temperature"] = (
            request.temperature
            if request.temperature is not None
            else self.config.temperature
        )
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop:
            body["stop_sequences"] = list(request.stop)
        return body

    def _parse_response(self, payload: dict[str, Any]) -> ChatResponse:
        content_blocks = payload.get("content") or []
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
        text = "".join(text_parts)
        usage = payload.get("usage") or {}
        return ChatResponse(
            model=str(payload.get("model", self.config.default_model)),
            message=ChatMessage(role=Role.ASSISTANT, content=text),
            finish_reason=payload.get("stop_reason"),
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            total_tokens=int(
                (usage.get("input_tokens", 0) or 0)
                + (usage.get("output_tokens", 0) or 0)
            ),
            raw=payload,
        )

    # Anthropic does not expose a public embeddings endpoint; we
    # surface a clear error rather than a confusing 404.
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:  # type: ignore[override]
        from forgecli.core.errors import ProviderError

        raise ProviderError(
            f"{self.name} does not provide embeddings in this build"
        )

    def _format_embeddings(self, request: EmbeddingRequest) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def _parse_embeddings(self, payload: dict[str, Any]) -> EmbeddingResponse:  # pragma: no cover
        raise NotImplementedError

    def _default_embedding_model(self) -> str:  # pragma: no cover
        return ""

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="claude-3-5-sonnet-latest", context_window=200_000, supports_tools=True, supports_vision=True),
            ModelInfo(id="claude-3-5-haiku-latest", context_window=200_000, supports_tools=True),
            ModelInfo(id="claude-3-opus-latest", context_window=200_000, supports_tools=True, supports_vision=True),
        ]


__all__ = ["AnthropicConfig", "AnthropicProvider"]
