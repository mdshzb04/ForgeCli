"""Smoke test for the CLI Typer app."""

from __future__ import annotations

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
    assert "mock" in result.output
