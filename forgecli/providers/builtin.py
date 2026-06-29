"""Built-in providers.

The package ships with the following implementations:

* :class:`MockProvider` — deterministic, offline-friendly, used in tests.
* :class:`OpenAIProvider` — OpenAI Chat Completions + Embeddings.
* :class:`AnthropicProvider` — Anthropic Messages API.
* :class:`GeminiProvider` — Google Gemini generateContent + embedContent.

All four register themselves into :data:`default_registry` on import.
"""

from forgecli.providers.anthropic import AnthropicConfig, AnthropicProvider
from forgecli.providers.google import GeminiConfig, GeminiProvider
from forgecli.providers.mock import MockProvider
from forgecli.providers.openai import OpenAIConfig, OpenAIProvider

__all__ = [
    "AnthropicConfig",
    "AnthropicProvider",
    "GeminiConfig",
    "GeminiProvider",
    "MockProvider",
    "OpenAIConfig",
    "OpenAIProvider",
]
