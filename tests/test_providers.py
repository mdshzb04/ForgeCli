"""Tests for the mock provider and provider registry."""

from __future__ import annotations

import asyncio

import pytest

from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
    ProviderRegistry,
    Role,
)
from forgecli.providers.mock import MockProvider, MockProviderConfig


def test_registry_register_and_resolve() -> None:
    registry = ProviderRegistry()
    registry.register("mock", MockProvider)
    provider = registry.create("mock", MockProviderConfig())
    assert isinstance(provider, MockProvider)
    assert "mock" in registry.names()


def test_registry_rejects_non_provider() -> None:
    registry = ProviderRegistry()

    class _NotAProvider:
        pass

    with pytest.raises(Exception):
        registry.register("bad", _NotAProvider)  # type: ignore[arg-type]


def test_mock_chat_echoes_user_message() -> None:
    provider = MockProvider(MockProviderConfig())
    request = ChatRequest(
        model="mock-model",
        messages=[ChatMessage(role=Role.USER, content="hello world")],
    )
    response = asyncio.run(provider.chat(request))
    assert response.message.content == "[mock] hello world"
    assert response.model == "mock-model"


def test_mock_embed_returns_vectors() -> None:
    provider = MockProvider(MockProviderConfig())
    request = EmbeddingRequest(inputs=["a", "b"])
    response = asyncio.run(provider.embed(request))
    assert len(response.vectors) == 2
    assert all(len(v) == 16 for v in response.vectors)


def test_mock_stream_yields_chunks() -> None:
    provider = MockProvider(MockProviderConfig())
    request = ChatRequest(
        model="mock-model",
        messages=[ChatMessage(role=Role.USER, content="hi")],
    )

    async def _collect() -> list[str]:
        parts: list[str] = []
        async for chunk in provider.stream(request):
            parts.append(chunk.delta)
        return parts

    parts = asyncio.run(_collect())
    assert any("mock" in p for p in parts)
