"""Smoke test for the CLI Typer app."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from forgecli import __version__
from forgecli.cli.main import app


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "ForgeCLI" in result.output


def test_cli_providers_list() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    # New providers list shows display names for real providers
    assert "OpenAI" in result.output or "Anthropic" in result.output or "Groq" in result.output


def test_cli_status() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Workspace Status" in result.output


def test_cli_info() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Information" in result.output


def test_cli_update(monkeypatch) -> None:
    from datetime import UTC, datetime

    from forgecli.platform.update import UpdateInfo

    dummy_info = UpdateInfo(
        current="0.1.0",
        latest="0.2.0",
        update_available=True,
        checked_at=datetime.now(UTC),
    )
    monkeypatch.setattr("forgecli.cli.commands_update.check_for_update", lambda **kwargs: dummy_info)

    runner = CliRunner()
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "Update Available!" in result.output


def test_cli_main_empty() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "ForgeCLI" in result.output
    assert "Developer Operating System" in result.output





def test_cli_records_history(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    result_history = runner.invoke(app, ["history", "list"])
    assert result_history.exit_code == 0
    assert "status" in result_history.output


def test_cli_verbose_logging(monkeypatch, tmp_path: Path) -> None:
    import logging
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    # Reset logger configuration so it configures anew
    from forgecli.core import logging as forge_logging
    old_configured = forge_logging._configured
    old_level = logging.getLogger().level
    forge_logging._configured = False

    try:
        runner = CliRunner()
        result = runner.invoke(app, ["--verbose", "status"])
        assert result.exit_code == 0
        assert logging.getLogger().level == logging.DEBUG
    finally:
        forge_logging._configured = old_configured
        logging.getLogger().setLevel(old_level)


def test_cli_doctor_output() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Overall Health" in result.output
    assert "Weighted Category Breakdown" in result.output
    assert "Deductions & Actionable Next Steps" in result.output



