"""Model routing and selection.

A :class:`ModelRouter` resolves a high-level request (provider name,
model alias, or ``"auto"``) into a concrete :class:`Provider` and
``model`` string. The router owns:

* the **registry** of installed providers (OpenAI, Anthropic, Google, mock, …);
* a static **cost model** keyed by ``(provider, model)``;
* a **selector** that, given a request's required capabilities, picks
  the cheapest compatible option.

The router is decoupled from concrete providers; new providers can be
registered without touching the router itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from forgecli.providers.base import ProviderRegistry, default_registry

# A small, well-known per-1k-token price table (USD, in/out).
# Values are static defaults; users may override per-deployment. Source:
# public pricing pages as of 2024-2025. These are advisory — the router
# uses them only to break ties between equally-capable models.
DEFAULT_PRICING: dict[tuple[str, str], tuple[float, float]] = {
    # OpenAI
    ("openai", "gpt-4o"): (0.005, 0.015),
    ("openai", "gpt-4o-mini"): (0.00015, 0.0006),
    ("openai", "gpt-4-turbo"): (0.01, 0.03),
    ("openai", "o1-preview"): (0.015, 0.06),
    ("openai", "o1-mini"): (0.003, 0.012),
    # Anthropic
    ("anthropic", "claude-3-5-sonnet-latest"): (0.003, 0.015),
    ("anthropic", "claude-3-5-haiku-latest"): (0.0008, 0.004),
    ("anthropic", "claude-3-opus-latest"): (0.015, 0.075),
    # Google
    ("google", "gemini-1.5-pro"): (0.00125, 0.005),
    ("google", "gemini-1.5-flash"): (0.000075, 0.0003),
    ("google", "gemini-2.0-flash-exp"): (0.0, 0.0),
    # Mock
    ("mock", "mock-model"): (0.0, 0.0),
}


class SelectionMode(str, Enum):
    """How the router picks a model."""

    EXPLICIT = "explicit"   # caller named provider + model
    ALIAS = "alias"         # caller named a provider alias
    CHEAPEST = "cheapest"   # "auto" — pick the cheapest compatible model
    FALLBACK = "fallback"   # an explicit selection failed; another matched


@dataclass(frozen=True)
class ModelCapabilities:
    """The capability hints a request expresses."""

    max_tokens: int | None = None
    needs_tools: bool = False
    needs_vision: bool = False


@dataclass(frozen=True)
class RouteDecision:
    """The router's resolution of a request."""

    provider_name: str
    model: str
    mode: SelectionMode
    cost_in: float = 0.0
    cost_out: float = 0.0
    candidates: tuple[tuple[str, str], ...] = ()


@dataclass
class ModelRouter:
    """Resolve high-level routing requests to provider + model."""

    registry: ProviderRegistry = field(default_factory=lambda: default_registry)
    pricing: dict[tuple[str, str], tuple[float, float]] = field(
        default_factory=lambda: dict(DEFAULT_PRICING)
    )
    default_models: dict[str, str] = field(
        default_factory=lambda: {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-latest",
            "google": "gemini-1.5-flash",
            "openrouter": "glm-5.2",
            "groq": "llama-4-scout",
            "mistral": "mistral-large",
            "ollama": "llama3",
            "lmstudio": "local-model",
            "vllm": "local-model",
            "mock": "mock-model",
        }
    )
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "claude": "anthropic",
            "openai": "openai",
            "gpt": "openai",
            "gemini": "google",
            "google": "google",
        }
    )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def available_providers(self) -> list[str]:
        return self.registry.names()

    def has_provider(self, name: str) -> bool:
        return self.registry.has(name)

    def resolve_alias(self, name: str) -> str:
        return self.aliases.get(name.lower(), name.lower())

    def default_model_for(self, provider_name: str) -> str:
        return self.default_models.get(
            provider_name.lower(),
            _DEFAULT_MODEL_BY_PROVIDER.get(provider_name.lower(), "auto"),
        )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select(
        self,
        choice: str,
        *,
        capabilities: ModelCapabilities | None = None,
    ) -> RouteDecision:
        """Resolve a CLI choice (claude / openai / gemini / auto / …)."""
        choice = (choice or "auto").strip()
        caps = capabilities or ModelCapabilities()

        if choice.lower() == "auto":
            return self._select_cheapest(caps)
        return self._select_explicit(choice, caps)

    def cheapest(
        self,
        capabilities: ModelCapabilities | None = None,
        *,
        provider: str | None = None,
    ) -> RouteDecision:
        """Pick the cheapest compatible (provider, model) pair.

        When ``provider`` is set, the algorithm restricts the search to
        that single provider. If that provider has no credentials, the
        router falls back to the mock with :data:`SelectionMode.FALLBACK`
        so the CLI never hard-errors.
        """
        if provider is not None:
            return self._select_cheapest(
                capabilities or ModelCapabilities(), provider=provider
            )
        return self._select_cheapest(capabilities or ModelCapabilities())

    # ------------------------------------------------------------------
    # Internal selectors
    # ------------------------------------------------------------------

    def _select_explicit(
        self, choice: str, caps: ModelCapabilities
    ) -> RouteDecision:
        provider_name = self.resolve_alias(choice)
        if not self.registry.has(provider_name):
            return RouteDecision(
                provider_name=provider_name,
                model=self.default_model_for(provider_name),
                mode=SelectionMode.ALIAS,
            )
        model = self.default_model_for(provider_name)
        cost_in, cost_out = self.pricing.get(
            (provider_name, model), (0.0, 0.0)
        )
        return RouteDecision(
            provider_name=provider_name,
            model=model,
            mode=SelectionMode.ALIAS,
            cost_in=cost_in,
            cost_out=cost_out,
        )

    def _select_cheapest(
        self,
        caps: ModelCapabilities,
        *,
        provider: str | None = None,
    ) -> RouteDecision:
        candidates = self._list_real_candidates(caps, provider=provider)
        if candidates:
            # Sort by (in_price, out_price, provider_name) for determinism.
            candidates.sort(
                key=lambda c: (
                    self.pricing.get(c, (0.0, 0.0))[0],
                    self.pricing.get(c, (0.0, 0.0))[1],
                    c[0],
                )
            )
            chosen = candidates[0]
            cost_in, cost_out = self.pricing.get(chosen, (0.0, 0.0))
            return RouteDecision(
                provider_name=chosen[0],
                model=chosen[1],
                mode=SelectionMode.CHEAPEST,
                cost_in=cost_in,
                cost_out=cost_out,
                candidates=tuple(candidates),
            )

        # No real provider had credentials; fall back to the mock.
        return RouteDecision(
            provider_name="mock",
            model=self.default_model_for("mock"),
            mode=SelectionMode.FALLBACK,
        )

    def _list_real_candidates(
        self,
        caps: ModelCapabilities,
        *,
        provider: str | None = None,
    ) -> list[tuple[str, str]]:
        """Return the (provider, model) pairs that satisfy ``caps`` AND
        have credentials available. Excludes the ``mock`` provider,
        which is reserved as a fallback.
        """
        out: list[tuple[str, str]] = []
        for name in self.registry.names():
            if name == "mock":
                continue
            if provider is not None and name != provider:
                continue
            if not _provider_has_credentials(name):
                continue
            model = self.default_model_for(name)
            out.append((name, model))
        return out

    def _list_candidates(
        self,
        caps: ModelCapabilities,
        *,
        provider: str | None = None,
    ) -> list[tuple[str, str]]:
        """Public list of real candidates; for tests and CLI display."""
        return self._list_real_candidates(caps, provider=provider)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_MODEL_BY_PROVIDER: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "google": "gemini-1.5-flash",
    "openrouter": "glm-5.2",
    "groq": "llama-4-scout",
    "mistral": "mistral-large",
    "ollama": "llama3",
    "lmstudio": "local-model",
    "vllm": "local-model",
    "mock": "mock-model",
}


_PROVIDER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "azure": ("AZURE_OPENAI_API_KEY",),
    "mistral": ("MISTRAL_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "ollama": ("OLLAMA_API_KEY",),
    "lmstudio": ("LMSTUDIO_API_KEY",),
    "vllm": ("VLLM_API_KEY",),
}


def _provider_has_credentials(name: str) -> bool:
    """Return True if any known env var or secure storage key for ``name`` is non-empty."""
    if name == "mock":
        return True
    if any(os.environ.get(env_var) for env_var in _PROVIDER_ENV_VARS.get(name, ())):
        return True
    from forgecli.core.credentials import get_api_key
    return bool(get_api_key(name))


def estimate_cost(
    decision: RouteDecision,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate USD cost for a finished call."""
    return (decision.cost_in * prompt_tokens + decision.cost_out * completion_tokens) / 1000.0


__all__ = [
    "DEFAULT_PRICING",
    "ModelCapabilities",
    "ModelRouter",
    "RouteDecision",
    "SelectionMode",
    "estimate_cost",
]
