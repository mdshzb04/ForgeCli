"""Comprehensive tests for forge auth and forge provider commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from forgecli.cli.main import app

# ---------------------------------------------------------------------------
# forge auth tests
# ---------------------------------------------------------------------------


def test_auth_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "--help"])
    assert result.exit_code == 0
    assert "login" in result.output
    assert "list" in result.output
    assert "logout" in result.output
    assert "status" in result.output
    assert "remove" in result.output
    assert "verify" in result.output


def test_auth_list_empty(monkeypatch) -> None:
    """When no keys are stored, list shows the empty message."""
    monkeypatch.setattr(
        "forgecli.core.credentials.list_authenticated_providers",
        lambda: [],
    )
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "list"])
    assert result.exit_code == 0
    assert "No authenticated" in result.output or "forge auth login" in result.output


def test_auth_list_with_providers(monkeypatch) -> None:
    """When keys are stored, list shows them."""
    monkeypatch.setattr(
        "forgecli.core.credentials.list_authenticated_providers",
        lambda: ["openai", "groq"],
    )
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "list"])
    assert result.exit_code == 0
    assert "Openai" in result.output or "openai" in result.output.lower()
    assert "Groq" in result.output or "groq" in result.output.lower()


def test_auth_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "forgecli.core.credentials.list_authenticated_providers",
        lambda: ["openai"],
    )
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "Authentication Status" in result.output


def test_auth_logout(monkeypatch) -> None:
    deleted = []
    monkeypatch.setattr(
        "forgecli.core.credentials.delete_all_api_keys",
        lambda: deleted.append(True),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert "Logged out" in result.output or len(deleted) == 1


def test_auth_remove(monkeypatch) -> None:
    deleted = []
    monkeypatch.setattr(
        "forgecli.core.credentials.delete_api_key",
        lambda provider: deleted.append(provider),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "remove", "openai"])
    assert result.exit_code == 0
    assert "openai" in result.output.lower() or "Removed" in result.output


def test_auth_verify_no_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        "forgecli.core.credentials.list_authenticated_providers",
        lambda: [],
    )
    runner = CliRunner()
    result = runner.invoke(app, ["auth", "verify"])
    assert result.exit_code == 0
    assert "No authenticated" in result.output


def test_auth_verify_with_valid_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "forgecli.core.credentials.list_authenticated_providers",
        lambda: ["openai"],
    )
    monkeypatch.setattr(
        "forgecli.core.credentials.get_api_key",
        lambda provider: "sk-test-key",
    )
    monkeypatch.setattr(
        "forgecli.core.verification.verify_provider_key",
        lambda provider, key: True,
    )

    async def mock_verify(p, k):
        return True

    with patch("forgecli.cli.commands_auth.asyncio.run", return_value=True):
        runner = CliRunner()
        result = runner.invoke(app, ["auth", "verify"])
    assert result.exit_code == 0


def test_auth_login_with_provider_and_key(monkeypatch, tmp_path: Path) -> None:
    """Test login with --provider and --key bypasses wizard and stores credential."""
    monkeypatch.chdir(tmp_path)
    saved = {}

    async def mock_verify(provider, key):
        return True

    monkeypatch.setattr(
        "forgecli.core.credentials.set_api_key",
        lambda p, k: saved.update({p: k}) or True,
    )
    monkeypatch.setattr(
        "forgecli.config.writer.update_config",
        lambda **kw: None,
    )
    with patch("forgecli.cli.commands_auth.asyncio.run", return_value=True):
        runner = CliRunner()
        result = runner.invoke(app, ["auth", "login", "--provider", "openai", "--key", "sk-testkey"])
    assert result.exit_code == 0
    assert "Connection successful" in result.output or "saved" in result.output.lower()


def test_auth_login_invalid_key_then_exit(monkeypatch, tmp_path: Path) -> None:
    """If verify fails and user declines retry, exit code 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("forgecli.config.writer.update_config", lambda **kw: None)
    with patch("forgecli.cli.commands_auth.asyncio.run", return_value=False):
        runner = CliRunner()
        # Input 'n' to decline retry
        result = runner.invoke(
            app,
            ["auth", "login", "--provider", "openai", "--key", "bad-key"],
            input="n\n",
        )
    assert result.exit_code != 0 or "failed" in result.output.lower()


# ---------------------------------------------------------------------------
# forge provider tests
# ---------------------------------------------------------------------------


def test_provider_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "use" in result.output
    assert "current" in result.output


def test_provider_list() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "list"])
    assert result.exit_code == 0
    assert "OpenAI" in result.output
    assert "Anthropic" in result.output
    assert "Groq" in result.output


def test_provider_use_valid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    updated = {}
    monkeypatch.setattr(
        "forgecli.config.writer.update_config",
        lambda **kw: updated.update(kw),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "use", "openai"])
    assert result.exit_code == 0
    assert "OpenAI" in result.output or "changed" in result.output.lower()


def test_provider_use_invalid() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "use", "unknownprovider"])
    assert result.exit_code != 0


def test_provider_use_gemini_maps_to_google(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    updated = {}
    monkeypatch.setattr(
        "forgecli.config.writer.update_config",
        lambda **kw: updated.update(kw),
    )
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "use", "gemini"])
    assert result.exit_code == 0
    assert updated.get("default_provider") == "google"


def test_provider_current(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "current"])
    assert result.exit_code == 0
    assert "Current Provider" in result.output or "Mock" in result.output


# ---------------------------------------------------------------------------
# Credential storage unit tests
# ---------------------------------------------------------------------------


def test_credentials_set_and_get(monkeypatch) -> None:
    """set_api_key stores value, get_api_key retrieves it."""

    store = {}

    def fake_set(service, key, value):
        store[key] = value

    def fake_get(service, key):
        return store.get(key)

    monkeypatch.setattr("keyring.set_password", fake_set)
    monkeypatch.setattr("keyring.get_password", fake_get)

    from forgecli.core.credentials import get_api_key, set_api_key

    set_api_key("openai", "sk-test123")
    assert get_api_key("openai") == "sk-test123"


def test_credentials_delete(monkeypatch) -> None:

    deleted = []

    monkeypatch.setattr("keyring.delete_password", lambda s, k: deleted.append(k))
    monkeypatch.setattr("keyring.get_password", lambda s, k: None)

    from forgecli.core.credentials import delete_api_key

    delete_api_key("anthropic")
    assert "anthropic" in deleted


def test_credentials_list_authenticated(monkeypatch) -> None:
    store = {"openai": "sk-test", "groq": "gsk_test"}

    monkeypatch.setattr(
        "keyring.get_password",
        lambda service, key: store.get(key),
    )
    monkeypatch.setattr("keyring.set_password", lambda s, k, v: None)

    from forgecli.core.credentials import list_authenticated_providers

    auth_list = list_authenticated_providers()
    assert "openai" in auth_list
    assert "groq" in auth_list
    assert "mistral" not in auth_list


def test_credentials_encrypted_fallback(tmp_path: Path, monkeypatch) -> None:
    """When keyring fails, credentials fall back to encrypted file."""
    monkeypatch.setattr("keyring.set_password", lambda *a: (_ for _ in ()).throw(RuntimeError("no keyring")))
    monkeypatch.setattr("keyring.get_password", lambda *a: None)
    monkeypatch.setattr(
        "forgecli.core.credentials._get_credentials_file",
        lambda: tmp_path / "credentials.json",
    )

    from forgecli.core.credentials import get_api_key, set_api_key

    result = set_api_key("mistral", "test-mistral-key")
    assert result is False  # stored in file
    retrieved = get_api_key("mistral")
    assert retrieved == "test-mistral-key"
