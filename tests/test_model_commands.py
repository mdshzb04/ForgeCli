"""Tests for the model router state and the ``forge model`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from forgecli.cli.main import app
from forgecli.providers.router_state import (
    RouterState,
    load_state,
    save_state,
)


def test_state_round_trip(tmp_path: Path) -> None:
    state = RouterState(choice="claude", model="claude-3-5-sonnet-latest", provider="anthropic")
    save_state(tmp_path / "router.json", state)
    loaded = load_state(tmp_path / "router.json")
    assert loaded == state


def test_load_state_missing_file(tmp_path: Path) -> None:
    assert load_state(tmp_path / "missing.json") == RouterState()


def test_load_state_handles_corrupt_json(tmp_path: Path) -> None:
    target = tmp_path / "router.json"
    target.write_text("not json", encoding="utf-8")
    assert load_state(target) == RouterState()


def test_state_to_extras_round_trip() -> None:
    state = RouterState(choice="claude", model="m", provider="anthropic")
    extras = state.to_extras()
    assert extras["router.choice"] == "claude"
    assert extras["router.model"] == "m"
    assert extras["router.provider"] == "anthropic"
    parsed = RouterState.from_extras(extras)
    assert parsed == state


def test_state_from_extras_defaults() -> None:
    state = RouterState.from_extras({})
    assert state.choice == "auto"
    assert state.model is None
    assert state.provider is None


def test_cli_model_auto(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    # Ensure no provider creds are set; auto should fall back to mock.
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    runner = CliRunner()
    result = runner.invoke(app, ["model", "auto"])
    assert result.exit_code == 0
    # State should have been persisted.
    persisted = json.loads((tmp_path / "router.json").read_text(encoding="utf-8"))
    assert persisted["choice"] == "auto"


def test_cli_model_claude_persists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["model", "claude"])
    assert result.exit_code == 0
    persisted = json.loads((tmp_path / "router.json").read_text(encoding="utf-8"))
    assert persisted["choice"] == "claude"


def test_cli_model_status_works(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["model", "status"])
    assert result.exit_code == 0


def test_cli_model_list_works(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0
    # All four built-in providers should be listed.
    output = result.output
    for name in ("openai", "anthropic", "google", "mock"):
        assert name in output


def test_cli_model_preview_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["model", "openai", "--model", "gpt-4o"])
    assert result.exit_code == 0
    result_preview = runner.invoke(app, ["model", "preview"])
    assert result_preview.exit_code == 0
    assert "gpt-4o" in result_preview.output
    assert "gpt-4o-mini" not in result_preview.output

