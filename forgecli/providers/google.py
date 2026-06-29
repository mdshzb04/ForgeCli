"""Google Gemini (Generative Language API) provider.

Targets the public ``https://generativelanguage.googleapis.com/v1beta``
endpoint. The provider follows the modern ``generateContent`` schema,
translating ChatRequest/Response into Gemini's ``contents`` array and
mapping the ``usageMetadata`` token counters back to the unified
format.

API keys are read from ``GOOGLE_API_KEY`` (with ``GEMINI_API_KEY`` as
a fallback) and are passed as the ``key`` query parameter, matching
the public REST contract.
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
class GeminiConfig:
    """Configuration for the Google Gemini provider."""

    api_key_env: str = "GOOGLE_API_KEY"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    default_model: str = "gemini-1.5-flash"
    max_tokens: int = 4096
    temperature: float = 0.2
    embeddings_model: str = "text-embedding-004"


_GEMINI_ROLE_MAP: dict[Role, str] = {
    Role.SYSTEM: "user",   # Gemini has no "system" role; fold into a user turn
    Role.USER: "user",
    Role.ASSISTANT: "model",
    Role.TOOL: "user",
}


class GeminiProvider(HTTPChatProvider):
    """Google Gemini generateContent + embedContent provider."""

    name = "google"

    def __init__(
        self,
        config: GeminiConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or GeminiConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )
        if not self._api_key:
            # Fall back to the alternate env var; this is intentional.
            self._api_key = _fallback_api_key(self.config.api_key_env)

    def _default_base_url(self) -> str:
        return "https://generativelanguage.googleapis.com/v1beta"

    def _chat_url(self) -> str:
        # The Gemini chat URL embeds the model name; we use
        # ``_chat_url_for`` instead. The fallback is here so abstract
        # callers can still get a URL when they have no request.
        return (
            f"{self._base_url}/models/{self.config.default_model}:generateContent"
            f"?key={self._api_key or ''}"
        )

    def _chat_url_for(self, request) -> str:  # type: ignore[override]
        model = request.model or self.config.default_model
        return (
            f"{self._base_url}/models/{model}:generateContent"
            f"?key={self._api_key or ''}"
        )

    def _embeddings_url(self) -> str:
        return (
            f"{self._base_url}/models/{self.config.embeddings_model}:embedContent"
            f"?key={self._api_key or ''}"
        )

    def _default_embedding_model(self) -> str:
        return self.config.embeddings_model

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        # Gemini uses the API key in the query string; no headers needed.
        return {"Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # Request / response
    # ------------------------------------------------------------------

    def _format_request(self, request: ChatRequest) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        system_parts: list[str] = []
        for message in request.messages:
            if message.role is Role.SYSTEM:
                if message.content:
                    system_parts.append(message.content)
                continue
            contents.append(
                {
                    "role": _GEMINI_ROLE_MAP[message.role],
                    "parts": [{"text": message.content}],
                }
            )
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens or self.config.max_tokens,
                "temperature": (
                    request.temperature
                    if request.temperature is not None
                    else self.config.temperature
                ),
            },
        }
        if system_parts:
            body["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }
        if request.top_p is not None:
            body["generationConfig"]["topP"] = request.top_p
        if request.stop:
            body["generationConfig"]["stopSequences"] = list(request.stop)
        return body

    def _parse_response(self, payload: dict[str, Any]) -> ChatResponse:
        candidates = payload.get("candidates") or []
        first = candidates[0] if candidates else {}
        content = first.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
        usage = payload.get("usageMetadata") or {}
        return ChatResponse(
            model=str(payload.get("modelVersion", self.config.default_model)),
            message=ChatMessage(role=Role.ASSISTANT, content=text),
            finish_reason=first.get("finishReason"),
            prompt_tokens=int(usage.get("promptTokenCount", 0) or 0),
            completion_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
            total_tokens=int(usage.get("totalTokenCount", 0) or 0),
            raw=payload,
        )

    def _format_embeddings(self, request: EmbeddingRequest) -> dict[str, Any]:
        # The Gemini embedContent endpoint takes a single ``content``
        # object; we issue one request per input to keep the wire
        # format simple. Callers that need batching should compose it
        # at a higher level.
        if len(request.inputs) != 1:
            from forgecli.core.errors import ProviderError

            raise ProviderError(
                f"{self.name} embed() expects exactly one input; got "
                f"{len(request.inputs)}"
            )
        return {
            "content": {
                "parts": [{"text": request.inputs[0]}],
            }
        }

    def _parse_embeddings(self, payload: dict[str, Any]) -> EmbeddingResponse:
        embedding = payload.get("embedding") or {}
        values = list(embedding.get("values", []))
        return EmbeddingResponse(
            model=str(payload.get("model", self.config.embeddings_model)),
            vectors=[values],
        )

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="gemini-1.5-pro", context_window=2_000_000, supports_tools=True, supports_vision=True),
            ModelInfo(id="gemini-1.5-flash", context_window=1_000_000, supports_tools=True, supports_vision=True),
            ModelInfo(id="gemini-2.0-flash-exp", context_window=1_000_000, supports_tools=True, supports_vision=True),
        ]


def _fallback_api_key(primary: str) -> str | None:
    """Read ``primary`` or ``GEMINI_API_KEY`` from the environment."""
    import os

    return os.environ.get(primary) or os.environ.get("GEMINI_API_KEY")


__all__ = ["GeminiConfig", "GeminiProvider"]
