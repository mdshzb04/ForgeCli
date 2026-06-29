"""Abstract base classes and shared data types for AI providers."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from forgecli.core.errors import ProviderError


class Role(str, Enum):
    """A role in a chat conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a chat conversation."""

    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ChatRequest(BaseModel):
    """Provider-agnostic chat completion request."""

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Provider-agnostic chat completion response."""

    model_config = ConfigDict(extra="allow")

    model: str
    message: ChatMessage
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class StreamChunk:
    """A piece of a streamed chat response."""

    delta: str
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    """Provider-agnostic embedding request."""

    model_config = ConfigDict(extra="allow")

    model: str | None = None
    inputs: list[str] = Field(default_factory=list)


class EmbeddingResponse(BaseModel):
    """Provider-agnostic embedding response."""

    model_config = ConfigDict(extra="allow")

    model: str
    vectors: list[list[float]] = Field(default_factory=list)
    prompt_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing a model exposed by a provider."""

    id: str
    name: str | None = None
    context_window: int | None = None
    supports_tools: bool = False
    supports_vision: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


TConfig = TypeVar("TConfig")


class Provider(ABC, Generic[TConfig]):
    """Base class for AI providers.

    Concrete providers should subclass :class:`Provider` with a concrete
    ``TConfig`` type and implement the abstract methods below.
    """

    name: str = "abstract"

    def __init__(self, config: TConfig) -> None:
        self._config = config

    @property
    def config(self) -> TConfig:
        return self._config

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send ``request`` and return a :class:`ChatResponse`."""

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream a chat response. Default falls back to a single chunk."""
        response = await self.chat(request)
        yield StreamChunk(
            delta=response.message.content,
            finish_reason=response.finish_reason,
            raw=response.raw,
        )
        return

    @abstractmethod
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Compute embeddings for ``request.inputs``."""

    async def list_models(self) -> list[ModelInfo]:
        """Return the list of models supported by this provider."""
        return []

    def validate(self) -> None:
        """Hook for pre-flight checks (API key, base URL, etc)."""
        return None

    @staticmethod
    def resolve_api_key(env_var: str | None) -> str | None:
        """Return the API key from ``env_var`` or ``None``."""
        if not env_var:
            return None
        return os.environ.get(env_var)


class ProviderRegistry:
    """In-memory registry of provider classes keyed by name."""

    def __init__(self) -> None:
        self._providers: dict[str, type[Provider[Any]]] = {}

    def register(self, name: str, provider_cls: type[Provider[Any]]) -> None:
        if not issubclass(provider_cls, Provider):
            raise ProviderError(
                f"{provider_cls!r} must subclass forgecli.providers.Provider"
            )
        if name in self._providers and self._providers[name] is not provider_cls:
            raise ProviderError(f"Provider {name!r} already registered")
        self._providers[name] = provider_cls

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def create(self, name: str, config: Any) -> Provider[Any]:
        cls = self._providers.get(name)
        if cls is None:
            raise ProviderError(f"Unknown provider: {name!r}")
        return cls(config)

    def names(self) -> list[str]:
        return sorted(self._providers)

    def has(self, name: str) -> bool:
        return name in self._providers


# A default registry instance used by ``AppContext`` wiring.
default_registry = ProviderRegistry()


def iter_chunked(items: list[str], size: int) -> Iterator[list[str]]:
    """Yield ``items`` in fixed-size chunks; useful for batched embedding calls."""
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for i in range(0, len(items), size):
        yield items[i : i + size]
