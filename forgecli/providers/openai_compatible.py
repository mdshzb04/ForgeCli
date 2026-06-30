"""OpenAI-compatible AI providers (OpenRouter, Groq, Mistral, Ollama, LM Studio, vLLM)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from forgecli.providers.base import ModelInfo
from forgecli.providers.http_base import HTTPChatProvider, messages_to_openai

# ---------------------------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------------------------

@dataclass
class OpenRouterConfig:
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    default_model: str = "glm-5.2"
    max_tokens: int = 4096
    temperature: float = 0.2


class OpenRouterProvider(HTTPChatProvider):
    name = "openrouter"

    def __init__(
        self,
        config: OpenRouterConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or OpenRouterConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://openrouter.ai/api/v1"

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _format_request(self, request: Any) -> dict[str, Any]:
        body = {
            "model": request.model or self.config.default_model,
            "messages": messages_to_openai(request.messages),
            "temperature": request.temperature if request.temperature is not None else self.config.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
        }
        return body

    def _parse_response(self, payload: dict[str, Any]) -> Any:
        # standard OpenAI response parsing
        from forgecli.providers.openai import OpenAIProvider
        # Re-use OpenAI's parser logic
        temp_provider = OpenAIProvider()
        return temp_provider._parse_response(payload)

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="glm-5.2", context_window=128_000, supports_tools=True),
            ModelInfo(id="deepseek-v3", context_window=128_000, supports_tools=True),
            ModelInfo(id="deepseek-r1", context_window=128_000, supports_tools=True),
            ModelInfo(id="qwen3-coder", context_window=128_000, supports_tools=True),
            ModelInfo(id="qwen3-32b", context_window=128_000, supports_tools=True),
            ModelInfo(id="kimi-k2", context_window=128_000, supports_tools=True),
            ModelInfo(id="llama-4-maverick", context_window=128_000, supports_tools=True),
            ModelInfo(id="llama-3.3-70b", context_window=128_000, supports_tools=True),
            ModelInfo(id="gemma-3", context_window=128_000, supports_tools=True),
            ModelInfo(id="devstral", context_window=128_000, supports_tools=True),
            ModelInfo(id="codestral", context_window=128_000, supports_tools=True),
        ]


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

@dataclass
class GroqConfig:
    api_key_env: str = "GROQ_API_KEY"
    base_url: str = "https://api.groq.com/openai/v1"
    default_model: str = "llama-4-scout"
    max_tokens: int = 4096
    temperature: float = 0.2


class GroqProvider(HTTPChatProvider):
    name = "groq"

    def __init__(
        self,
        config: GroqConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or GroqConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.groq.com/openai/v1"

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _format_request(self, request: Any) -> dict[str, Any]:
        return {
            "model": request.model or self.config.default_model,
            "messages": messages_to_openai(request.messages),
            "temperature": request.temperature if request.temperature is not None else self.config.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
        }

    def _parse_response(self, payload: dict[str, Any]) -> Any:
        from forgecli.providers.openai import OpenAIProvider
        temp_provider = OpenAIProvider()
        return temp_provider._parse_response(payload)

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="llama-4-scout", context_window=128_000, supports_tools=True),
            ModelInfo(id="deepseek-r1", context_window=128_000, supports_tools=True),
            ModelInfo(id="qwen3-32b", context_window=128_000, supports_tools=True),
        ]


# ---------------------------------------------------------------------------
# Mistral
# ---------------------------------------------------------------------------

@dataclass
class MistralConfig:
    api_key_env: str = "MISTRAL_API_KEY"
    base_url: str = "https://api.mistral.ai/v1"
    default_model: str = "mistral-large"
    max_tokens: int = 4096
    temperature: float = 0.2


class MistralProvider(HTTPChatProvider):
    name = "mistral"

    def __init__(
        self,
        config: MistralConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or MistralConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.mistral.ai/v1"

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _format_request(self, request: Any) -> dict[str, Any]:
        return {
            "model": request.model or self.config.default_model,
            "messages": messages_to_openai(request.messages),
            "temperature": request.temperature if request.temperature is not None else self.config.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
        }

    def _parse_response(self, payload: dict[str, Any]) -> Any:
        from forgecli.providers.openai import OpenAIProvider
        temp_provider = OpenAIProvider()
        return temp_provider._parse_response(payload)

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="mistral-large", context_window=128_000, supports_tools=True),
            ModelInfo(id="magistral", context_window=128_000, supports_tools=True),
            ModelInfo(id="mistral-small", context_window=128_000, supports_tools=True),
        ]


# ---------------------------------------------------------------------------
# Local Providers
# ---------------------------------------------------------------------------

class LocalProvider(HTTPChatProvider):
    """Generic base class for local providers that support dynamic model list query."""

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _format_request(self, request: Any) -> dict[str, Any]:
        return {
            "model": request.model or self.config.default_model,
            "messages": messages_to_openai(request.messages),
            "temperature": request.temperature if request.temperature is not None else self.config.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
        }

    def _parse_response(self, payload: dict[str, Any]) -> Any:
        from forgecli.providers.openai import OpenAIProvider
        temp_provider = OpenAIProvider()
        return temp_provider._parse_response(payload)

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get(
                f"{self._base_url}/models",
                headers=self._auth_headers(),
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                models_list = data.get("data", [])
                return [
                    ModelInfo(
                        id=m.get("id"),
                        name=m.get("id"),
                        context_window=128_000,
                        supports_tools=True,
                        supports_vision=True
                    )
                    for m in models_list if isinstance(m, dict) and "id" in m
                ]
        except Exception:
            pass
        return self._known_models()


@dataclass
class OllamaConfig:
    api_key_env: str = "OLLAMA_API_KEY"
    base_url: str = "http://localhost:11434/v1"
    default_model: str = "llama3"
    max_tokens: int = 4096
    temperature: float = 0.2


class OllamaProvider(LocalProvider):
    name = "ollama"

    def __init__(
        self,
        config: OllamaConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or OllamaConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "http://localhost:11434/v1"

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="llama3", context_window=8192, supports_tools=True),
        ]


@dataclass
class LMStudioConfig:
    api_key_env: str = "LMSTUDIO_API_KEY"
    base_url: str = "http://localhost:1234/v1"
    default_model: str = "local-model"
    max_tokens: int = 4096
    temperature: float = 0.2


class LMStudioProvider(LocalProvider):
    name = "lmstudio"

    def __init__(
        self,
        config: LMStudioConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or LMStudioConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "http://localhost:1234/v1"

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="local-model", context_window=8192, supports_tools=True),
        ]


@dataclass
class VllmConfig:
    api_key_env: str = "VLLM_API_KEY"
    base_url: str = "http://localhost:8000/v1"
    default_model: str = "local-model"
    max_tokens: int = 4096
    temperature: float = 0.2


class VllmProvider(LocalProvider):
    name = "vllm"

    def __init__(
        self,
        config: VllmConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or VllmConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "http://localhost:8000/v1"

    def _known_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(id="local-model", context_window=8192, supports_tools=True),
        ]
