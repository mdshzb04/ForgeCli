"""OpenAI Chat Completions provider.

Targets the public ``https://api.openai.com/v1`` endpoint, with sane
defaults for the most common models (gpt-4o, gpt-4o-mini, o1, …). The
provider is configured via the standard ``OPENAI_API_KEY`` environment
variable; the base URL can be overridden in the ForgeCLI config to
point at OpenAI-compatible servers (vLLM, LM Studio, llama.cpp).
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
from forgecli.providers.http_base import HTTPChatProvider, messages_to_openai


@dataclass
class OpenAIConfig:
    """Configuration for the OpenAI provider."""

    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.2
    embeddings_model: str = "text-embedding-3-small"


class OpenAIProvider(HTTPChatProvider):
    """OpenAI Chat Completions + Embeddings."""

    name = "openai"

    def __init__(
        self,
        config: OpenAIConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or OpenAIConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.openai.com/v1"

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _embeddings_url(self) -> str:
        return f"{self._base_url}/embeddings"

    def _default_embedding_model(self) -> str:
        return self.config.embeddings_model

    def _format_request(self, request: ChatRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model or self.config.default_model,
            "messages": messages_to_openai(request.messages),
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        else:
            body["temperature"] = self.config.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        else:
            body["max_tokens"] = self.config.max_tokens
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop:
            body["stop"] = list(request.stop)
        if request.tools:
            body["tools"] = list(request.tools)
        return body

    def _parse_response(self, payload: dict[str, Any]) -> ChatResponse:
        choices = payload.get("choices") or []
        first = choices[0] if choices else {}
        message = first.get("message") or {}
        usage = payload.get("usage") or {}
        return ChatResponse(
            model=str(payload.get("model", self.config.default_model)),
            message=ChatMessage(
                role=Role(message.get("role", "assistant")),
                content=str(message.get("content", "")),
            ),
            finish_reason=first.get("finish_reason"),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
            raw=payload,
        )

    def _format_embeddings(self, request: EmbeddingRequest) -> dict[str, Any]:
        return {
            "model": request.model or self.config.embeddings_model,
            "input": list(request.inputs),
        }

    def _parse_embeddings(self, payload: dict[str, Any]) -> EmbeddingResponse:
        data = payload.get("data") or []
        vectors = [list(item.get("embedding", [])) for item in data]
        usage = payload.get("usage") or {}
        return EmbeddingResponse(
            model=str(payload.get("model", self.config.embeddings_model)),
            vectors=vectors,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
        )

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="gpt-4o", context_window=128_000, supports_tools=True, supports_vision=True),
            ModelInfo(id="gpt-4o-mini", context_window=128_000, supports_tools=True, supports_vision=True),
            ModelInfo(id="gpt-4-turbo", context_window=128_000, supports_tools=True, supports_vision=True),
            ModelInfo(id="o1-preview", context_window=128_000, supports_tools=False),
            ModelInfo(id="o1-mini", context_window=128_000, supports_tools=False),
        ]


__all__ = ["OpenAIConfig", "OpenAIProvider"]
