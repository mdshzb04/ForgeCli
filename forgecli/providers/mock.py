"""A deterministic provider used in tests and offline development."""

from __future__ import annotations

import hashlib
from typing import ClassVar

from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    Provider,
    Role,
    StreamChunk,
)


class MockProviderConfig:
    """Configuration for :class:`MockProvider`."""

    def __init__(self, default_model: str = "mock-model", max_tokens: int = 1024) -> None:
        self.default_model = default_model
        self.max_tokens = max_tokens


class MockProvider(Provider[MockProviderConfig]):
    """Echoes the last user message and returns deterministic embeddings."""

    name: ClassVar[str] = "mock"
    _MODELS: ClassVar[list[ModelInfo]] = [
        ModelInfo(id="mock-model", name="Mock Model", context_window=8192),
    ]

    def __init__(self, config: MockProviderConfig | None = None) -> None:
        super().__init__(config or MockProviderConfig())

    async def chat(self, request: ChatRequest) -> ChatResponse:
        last_user = next(
            (m for m in reversed(request.messages) if m.role is Role.USER),
            None,
        )
        text = last_user.content if last_user else ""
        return ChatResponse(
            model=request.model or self.config.default_model,
            message=ChatMessage(role=Role.ASSISTANT, content=f"[mock] {text}"),
            finish_reason="stop",
            prompt_tokens=len(text),
            completion_tokens=len(text),
            total_tokens=len(text) * 2,
        )

    async def stream(self, request: ChatRequest):
        response = await self.chat(request)
        for word in response.message.content.split(" "):
            yield StreamChunk(delta=word + " ", raw=response.raw)
        yield StreamChunk(delta="", finish_reason="stop")

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors: list[list[float]] = []
        for text in request.inputs:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [b / 255.0 for b in digest[:16]]
            vectors.append(vec)
        return EmbeddingResponse(
            model=request.model or self.config.default_model,
            vectors=vectors,
            prompt_tokens=sum(len(t) for t in request.inputs),
            total_tokens=sum(len(t) for t in request.inputs),
        )

    async def list_models(self) -> list[ModelInfo]:
        return list(self._MODELS)
