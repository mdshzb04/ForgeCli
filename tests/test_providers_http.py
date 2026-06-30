"""Tests for the OpenAI, Anthropic, and Gemini providers via respx."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from forgecli.core.errors import ProviderError
from forgecli.providers.anthropic import AnthropicConfig, AnthropicProvider
from forgecli.providers.base import ChatMessage, ChatRequest, Role
from forgecli.providers.google import GeminiConfig, GeminiProvider
from forgecli.providers.openai import OpenAIConfig, OpenAIProvider


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_chat_posts_and_parses() -> None:
    openai_response = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 7,
            "total_tokens": 19,
        },
    }
    captured: dict[str, Any] = {}

    def _post(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=openai_response)

    provider = OpenAIProvider(
        config=OpenAIConfig(default_model="gpt-4o-mini"),
        api_key="sk-test",
        client=_client(),
    )
    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.openai.com/v1/chat/completions").mock(side_effect=_post)
        response = await provider.chat(
            ChatRequest(
                model="gpt-4o-mini",
                messages=[ChatMessage(role=Role.USER, content="hi")],
                temperature=0.1,
            )
        )

    assert response.message.content == "hello"
    assert response.model == "gpt-4o-mini"
    assert response.completion_tokens == 7
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["body"]["temperature"] == 0.1
    assert captured["headers"]["authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_openai_chat_raises_on_http_error() -> None:
    provider = OpenAIProvider(
        config=OpenAIConfig(),
        api_key="sk-test",
        client=_client(),
    )
    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(ProviderError, match="500"):
            await provider.chat(
                ChatRequest(messages=[ChatMessage(role=Role.USER, content="hi")])
            )


@pytest.mark.asyncio
async def test_openai_validate_raises_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("forgecli.core.credentials.get_api_key", lambda name: None)
    provider = OpenAIProvider(config=OpenAIConfig(), api_key=None, client=_client())
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        provider.validate()


@pytest.mark.asyncio
async def test_openai_embed_parses_vectors() -> None:
    embed_response = {
        "object": "list",
        "data": [{"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 0}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }
    provider = OpenAIProvider(
        config=OpenAIConfig(),
        api_key="sk-test",
        client=_client(),
    )
    from forgecli.providers.base import EmbeddingRequest

    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.openai.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=embed_response)
        )
        response = await provider.embed(EmbeddingRequest(inputs=["hi"]))
    assert response.vectors == [[0.1, 0.2, 0.3]]
    assert response.model == "text-embedding-3-small"


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_chat_uses_x_api_key_header() -> None:
    anthropic_response = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-5-haiku-latest",
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    captured: dict[str, Any] = {}

    def _post(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=anthropic_response)

    provider = AnthropicProvider(
        config=AnthropicConfig(),
        api_key="sk-ant-test",
        client=_client(),
    )
    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.anthropic.com/v1/messages").mock(side_effect=_post)
        response = await provider.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role=Role.SYSTEM, content="be terse"),
                    ChatMessage(role=Role.USER, content="hi"),
                ],
                model="claude-3-5-haiku-latest",
            )
        )
    assert response.message.content == "ok"
    assert response.prompt_tokens == 5
    assert response.completion_tokens == 3
    # System prompt was lifted out of the messages list.
    assert captured["body"]["system"] == "be terse"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_anthropic_embed_is_unsupported() -> None:
    from forgecli.providers.base import EmbeddingRequest

    provider = AnthropicProvider(
        config=AnthropicConfig(),
        api_key="sk-ant-test",
        client=_client(),
    )
    with pytest.raises(ProviderError, match="embeddings"):
        await provider.embed(EmbeddingRequest(inputs=["hi"]))


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_chat_uses_per_model_url() -> None:
    gemini_response = {
        "candidates": [
            {
                "content": {"parts": [{"text": "hi from gemini"}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "modelVersion": "gemini-1.5-flash",
        "usageMetadata": {
            "promptTokenCount": 4,
            "candidatesTokenCount": 5,
            "totalTokenCount": 9,
        },
    }
    captured: dict[str, Any] = {}

    def _post(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=gemini_response)

    provider = GeminiProvider(
        config=GeminiConfig(),
        api_key="goog-test",
        client=_client(),
    )
    async with respx.mock(assert_all_called=False) as mock:
        mock.post(url__regex=r".*generateContent.*").mock(side_effect=_post)
        response = await provider.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role=Role.SYSTEM, content="be brief"),
                    ChatMessage(role=Role.USER, content="hi"),
                ],
                model="gemini-1.5-flash",
            )
        )
    assert response.message.content == "hi from gemini"
    assert response.completion_tokens == 5
    # The URL embeds the model name and the API key as a query string.
    assert "models/gemini-1.5-flash:generateContent" in captured["url"]
    assert "key=goog-test" in captured["url"]
    # The system prompt was promoted to systemInstruction.
    assert "systemInstruction" in captured["body"]
    # The remaining contents include a user turn only (system was lifted).
    assert captured["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "hi"}]}
    ]


@pytest.mark.asyncio
async def test_gemini_embed_single_input() -> None:
    embed_response = {
        "embedding": {"values": [0.4, 0.5, 0.6]},
    }
    provider = GeminiProvider(
        config=GeminiConfig(),
        api_key="goog-test",
        client=_client(),
    )
    from forgecli.providers.base import EmbeddingRequest

    async with respx.mock(assert_all_called=False) as mock:
        mock.post(url__regex=r".*embedContent.*").mock(
            return_value=httpx.Response(200, json=embed_response)
        )
        response = await provider.embed(EmbeddingRequest(inputs=["hi"]))
    assert response.vectors == [[0.4, 0.5, 0.6]]


@pytest.mark.asyncio
async def test_gemini_embed_rejects_multiple_inputs() -> None:
    provider = GeminiProvider(
        config=GeminiConfig(),
        api_key="goog-test",
        client=_client(),
    )
    from forgecli.providers.base import EmbeddingRequest

    with pytest.raises(ProviderError, match="exactly one input"):
        await provider.embed(EmbeddingRequest(inputs=["a", "b"]))
