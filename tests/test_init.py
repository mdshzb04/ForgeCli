"""Tests for the ``forge init`` subcommand."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from forgecli.cli.main import app


def test_init_creates_directories_and_files(tmp_path: Path, monkeypatch) -> None:
    # Set up isolation env vars so we don't write to actual user home
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FORGECLI_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(data_dir))

    project_root = tmp_path / "my_project"
    project_root.mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--path", str(project_root)])
    assert result.exit_code == 0
    assert "ForgeCLI" in result.output
    assert "Directories" in result.output
    assert "Wrote config" in result.output
    assert "Wrote .env template" in result.output

    # Check files created
    config_file = project_root / "forgecli.toml"
    assert config_file.exists()
    assert "[app]" in config_file.read_text(encoding="utf-8")

    env_file = project_root / ".env"
    assert env_file.exists()
    assert "OPENAI_API_KEY" in env_file.read_text(encoding="utf-8")

    # Check directories are created
    assert config_dir.exists()
    assert data_dir.exists()


def test_init_json_output(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FORGECLI_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(data_dir))

    project_root = tmp_path / "json_project"
    project_root.mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--path", str(project_root), "--json"])
    assert result.exit_code == 0

    # Parse and validate JSON
    payload = json.loads(result.output)
    assert payload["project_root"] == str(project_root.resolve())
    assert payload["config_written"] is True
    assert payload["env_written"] is True
    assert "directories" in payload
    assert "doctor" in payload


def test_init_does_not_overwrite_existing_unless_forced(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FORGECLI_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(data_dir))

    project_root = tmp_path / "existing_project"
    project_root.mkdir()

    config_file = project_root / "forgecli.toml"
    config_file.write_text("existing_content = true", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--path", str(project_root)])
    assert result.exit_code == 0
    assert "Config already exists" in result.output
    assert config_file.read_text(encoding="utf-8") == "existing_content = true"

    # Now run with --force
    result_forced = runner.invoke(app, ["init", "--path", str(project_root), "--force"])
    assert result_forced.exit_code == 0
    assert "Wrote config" in result_forced.output
    assert "[app]" in config_file.read_text(encoding="utf-8")


def test_init_onboarding_copy(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FORGECLI_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(data_dir))

    project_root = tmp_path / "onboarding_project"
    project_root.mkdir()

    runner = CliRunner()
    result = runner.invoke(app, ["init", "--path", str(project_root)])
    assert result.exit_code == 0
    assert "✓ Ponytail prompt optimization is built-in." in result.output
    assert "✓ Graph intelligence is built-in" in result.output
    assert "configure an LLM API key" in result.output
    assert "semantic indexing" in result.output
    assert "uv tool install graphifyy" not in result.output

