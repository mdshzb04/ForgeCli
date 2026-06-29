"""Tests for the prompt renderer and registry."""

from __future__ import annotations

from forgecli.prompts.registry import PromptRegistry
from forgecli.prompts.renderer import PromptRenderer


def test_renderer_substitutes_variables() -> None:
    out = PromptRenderer().render("Hello {name}!", name="World")
    assert out == "Hello World!"


def test_registry_register_and_get() -> None:
    reg = PromptRegistry()
    reg.register("greeting", "Hi {name}")
    assert reg.get("greeting") == "Hi {name}"
    assert "greeting" in reg.names()
