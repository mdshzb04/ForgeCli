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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "openrouter"
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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "groq"
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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "mistral"
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
                        id=str(m["id"]),
                        name=str(m.get("id")),
                        context_window=128_000,
                        supports_tools=True,
                        supports_vision=True
                    )
                    for m in models_list if isinstance(m, dict) and m.get("id") is not None
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

    async def list_models(self) -> list[ModelInfo]:
        try:
            import subprocess
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) > 1:
                    models = []
                    for line in lines[1:]:
                        parts = line.split()
                        if parts:
                            model_id = parts[0]
                            models.append(
                                ModelInfo(
                                    id=model_id,
                                    name=model_id,
                                    context_window=8192,
                                    supports_tools=True
                                )
                            )
                    if models:
                        return models
        except Exception:
            pass
        return await super().list_models()

    def _known_models(self) -> list[ModelInfo]:
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=8192, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "ollama"
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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=8192, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "lmstudio"
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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=8192, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "vllm"
        ]


# ---------------------------------------------------------------------------
# MiniMax
# ---------------------------------------------------------------------------

@dataclass
class MiniMaxConfig:
    api_key_env: str = "MINIMAX_API_KEY"
    base_url: str = "https://api.minimaxi.chat/v1"
    default_model: str = "abab6.5g-chat"
    max_tokens: int = 4096
    temperature: float = 0.2


class MiniMaxProvider(HTTPChatProvider):
    name = "minimax"

    def __init__(
        self,
        config: MiniMaxConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or MiniMaxConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.minimaxi.chat/v1"

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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "minimax"
        ]


# ---------------------------------------------------------------------------
# xAI (Grok)
# ---------------------------------------------------------------------------

@dataclass
class XaiConfig:
    api_key_env: str = "XAI_API_KEY"
    base_url: str = "https://api.x.ai/v1"
    default_model: str = "grok-2"
    max_tokens: int = 4096
    temperature: float = 0.2


class XaiProvider(HTTPChatProvider):
    name = "xai"

    def __init__(
        self,
        config: XaiConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or XaiConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.x.ai/v1"

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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "xai"
        ]


# ---------------------------------------------------------------------------
# Together AI
# ---------------------------------------------------------------------------

@dataclass
class TogetherConfig:
    api_key_env: str = "TOGETHER_API_KEY"
    base_url: str = "https://api.together.xyz/v1"
    default_model: str = "llama-3.1-70b"
    max_tokens: int = 4096
    temperature: float = 0.2


class TogetherProvider(HTTPChatProvider):
    name = "together"

    def __init__(
        self,
        config: TogetherConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or TogetherConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.together.xyz/v1"

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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "together"
        ]


# ---------------------------------------------------------------------------
# Fireworks AI
# ---------------------------------------------------------------------------

@dataclass
class FireworksConfig:
    api_key_env: str = "FIREWORKS_API_KEY"
    base_url: str = "https://api.fireworks.ai/inference/v1"
    default_model: str = "llama-3.1-70b"
    max_tokens: int = 4096
    temperature: float = 0.2


class FireworksProvider(HTTPChatProvider):
    name = "fireworks"

    def __init__(
        self,
        config: FireworksConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or FireworksConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.fireworks.ai/inference/v1"

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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "fireworks"
        ]


# ---------------------------------------------------------------------------
# Cohere
# ---------------------------------------------------------------------------

@dataclass
class CohereConfig:
    api_key_env: str = "COHERE_API_KEY"
    base_url: str = "https://api.cohere.com/v1"
    default_model: str = "command-r-plus"
    max_tokens: int = 4096
    temperature: float = 0.2


class CohereProvider(HTTPChatProvider):
    name = "cohere"

    def __init__(
        self,
        config: CohereConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or CohereConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://api.cohere.com/v1"

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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "cohere"
        ]


# ---------------------------------------------------------------------------
# NVIDIA NIM
# ---------------------------------------------------------------------------

@dataclass
class NvidiaConfig:
    api_key_env: str = "NVIDIA_API_KEY"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    default_model: str = "llama-3.1-70b"
    max_tokens: int = 4096
    temperature: float = 0.2


class NvidiaProvider(HTTPChatProvider):
    name = "nvidia"

    def __init__(
        self,
        config: NvidiaConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            config or NvidiaConfig(),
            api_key=api_key,
            base_url=base_url,
            client=client,
        )

    def _default_base_url(self) -> str:
        return "https://integrate.api.nvidia.com/v1"

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
        from forgecli.core.models import MODEL_CATALOG
        return [
            ModelInfo(id=m.id, name=m.display_name, context_window=128_000, supports_tools=True)
            for m in MODEL_CATALOG if m.provider == "nvidia"
        ]
