"""Tests for the ModelRouter."""

from __future__ import annotations

import pytest

from forgecli.providers.anthropic import AnthropicProvider
from forgecli.providers.base import ModelInfo, Provider, ProviderRegistry
from forgecli.providers.google import GeminiProvider
from forgecli.providers.mock import MockProvider
from forgecli.providers.openai import OpenAIProvider
from forgecli.providers.router import (
    DEFAULT_PRICING,
    ModelRouter,
    SelectionMode,
    estimate_cost,
)



@pytest.fixture(autouse=True)
def mock_get_api_key(monkeypatch) -> None:
    monkeypatch.setattr("forgecli.core.credentials.get_api_key", lambda name: None)


def _registry_with_real_providers() -> ProviderRegistry:
    """Build a registry with mock + OpenAI + Anthropic + Gemini."""
    registry = ProviderRegistry()
    registry.register("mock", MockProvider)
    registry.register("openai", OpenAIProvider)
    registry.register("anthropic", AnthropicProvider)
    registry.register("google", GeminiProvider)
    return registry


def _registry_with_mock() -> ProviderRegistry:
    return _registry_with_real_providers()


def test_router_resolves_aliases() -> None:
    router = ModelRouter(registry=_registry_with_mock())
    assert router.resolve_alias("claude") == "anthropic"
    assert router.resolve_alias("OPENAI") == "openai"
    assert router.resolve_alias("gemini") == "google"
    assert router.resolve_alias("gpt") == "openai"
    assert router.resolve_alias("unknown") == "unknown"


def test_router_explicit_selection_uses_default_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    router = ModelRouter(registry=_registry_with_mock())
    decision = router.select("openai")
    assert decision.provider_name == "openai"
    assert decision.model == router.default_model_for("openai")
    assert decision.mode is SelectionMode.ALIAS


def test_router_explicit_selection_with_no_credentials(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    router = ModelRouter(registry=_registry_with_mock())
    decision = router.select("openai")
    # The decision is still made, but in auto mode no candidate will be openai.
    assert decision.provider_name == "openai"


def test_router_auto_picks_cheapest(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-2")
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-3")
    router = ModelRouter(registry=_registry_with_mock())
    decision = router.select("auto")
    assert decision.mode is SelectionMode.CHEAPEST
    # google/gemini-2.5-flash is the cheapest of the three default models.
    assert decision.provider_name == "google"
    assert decision.model == "gemini-2.5-flash"


def test_router_auto_falls_back_to_mock_when_no_creds(monkeypatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    router = ModelRouter(registry=_registry_with_mock())
    decision = router.select("auto")
    assert decision.mode is SelectionMode.FALLBACK
    assert decision.provider_name == "mock"


def test_router_cheapest_helper_matches_select(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-2")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    router = ModelRouter(registry=_registry_with_mock())
    via_select = router.select("auto")
    via_helper = router.cheapest()
    assert via_select.provider_name == via_helper.provider_name
    assert via_select.model == via_helper.model


def test_router_cheapest_can_filter_by_provider(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-2")
    router = ModelRouter(registry=_registry_with_mock())
    decision = router.cheapest(provider="anthropic")
    assert decision.provider_name == "anthropic"


def test_router_candidates_are_sorted_deterministically(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-2")
    monkeypatch.setenv("GOOGLE_API_KEY", "sk-3")
    router = ModelRouter(registry=_registry_with_mock())
    decision = router.select("auto")
    assert decision.candidates
    # The first candidate is the cheapest; check monotonic price.
    prices = [router.pricing.get(c, (0.0, 0.0))[0] for c in decision.candidates]
    assert prices == sorted(prices)


def test_router_capability_filtering() -> None:
    class _VisionProvider(Provider):
        name = "vision"

        def __init__(self) -> None:
            super().__init__(object())

        async def chat(self, request):  # pragma: no cover
            raise NotImplementedError

        async def embed(self, request):  # pragma: no cover
            raise NotImplementedError

        async def list_models(self):
            return [ModelInfo(id="vision-model", supports_vision=True)]

    registry = _registry_with_mock()
    registry.register("vision", _VisionProvider)
    router = ModelRouter(registry=registry)
    # Without capability hints the cheapest-compat path returns the
    # default model for whichever provider has credentials; we only
    # test the shape of the decision here.
    decision = router.select("vision")
    assert decision.provider_name == "vision"
    assert decision.mode is SelectionMode.ALIAS


def test_estimate_cost_uses_pricing_table() -> None:
    decision = ModelRouter(registry=_registry_with_mock()).select("auto")
    cost = estimate_cost(
        decision,
        prompt_tokens=1000,
        completion_tokens=500,
    )
    expected = (decision.cost_in * 1000 + decision.cost_out * 500) / 1000.0
    assert cost == pytest.approx(expected)


def test_default_pricing_has_three_families() -> None:
    providers = {p for p, _ in DEFAULT_PRICING}
    assert {"openai", "anthropic", "google"}.issubset(providers)
