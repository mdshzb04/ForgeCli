"""Smoke tests for the new subcommands (ask, docs, release)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from forgecli.cli.main import app

# ---------------------------------------------------------------------------
# forge ask
# ---------------------------------------------------------------------------


def test_cli_ask_runs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("forgecli.cli.commands_ask._run_ask", return_value=None) as mock:
        result = runner.invoke(app, ["ask", "What does the graph do?"])
    assert result.exit_code == 0
    mock.assert_called_once()


def test_cli_ask_requires_question() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["ask"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# forge docs
# ---------------------------------------------------------------------------


def test_cli_docs_writes_overview(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    project = tmp_path / "proj"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "mod.py").write_text("def hello():\n    return 'hi'\n")
    runner = CliRunner()
    result = runner.invoke(app, ["docs", "--path", str(project)])
    assert result.exit_code == 0
    assert (project / "docs" / "OVERVIEW.md").exists()


# ---------------------------------------------------------------------------
# forge release (dry-run)
# ---------------------------------------------------------------------------


def test_cli_release_dry_run_requires_unreleased(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    project = tmp_path / "proj"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["release", "--dry-run", "--path", str(project), "1.0.0"],
    )
    # No CHANGELOG.md → warns and exits 1.
    assert result.exit_code == 1


def test_cli_release_requires_semver(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["release", "not-a-version"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Top-level forge (--prompt)
# ---------------------------------------------------------------------------


def test_cli_top_level_forge_runs_pipeline(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    project = tmp_path / "proj"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--path",
            str(project),
            "--prompt",
            "Add a foo() function",
            "--no-tests",
            "--no-commit",
            "--json",
        ],
    )
    assert result.exit_code == 0
    import json
    payload = json.loads(result.output)
    assert payload["intent"] == "build"
    assert payload["workflow"] == "build"
    assert payload["success"] is True


def test_cli_top_level_forge_without_prompt_prints_usage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, [])
    # No subcommand and no --prompt → prints a usage hint.
    assert "Usage:" in result.output or result.exit_code == 0


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------


def test_plugin_registry_can_register_custom_workflow() -> None:
    from forgecli.plugins import Intent, PluginRegistry, Workflow

    class Custom(Workflow):
        name = "custom"
        intents = (Intent.ASK,)

        async def run(self, context):
            return {"summary": "custom ran", "files_touched": [], "diff": ""}

    registry = PluginRegistry()
    registry.register_workflow(Custom())
    assert any(w.name == "custom" for w in registry.workflows)


def test_cli_build_option_after_positional(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    # Mocking _run_build so we don't execute the entire pipeline
    with patch("forgecli.cli.commands_build._run_build", return_value=None) as mock_run:
        result = runner.invoke(app, ["build", "My build prompt", "--no-tests"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    assert mock_run.call_args[1]["no_tests"] is True


def test_cli_release_option_after_positional(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORGECLI_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["release", "1.0.0", "--dry-run"])
    # Should not fail with click argument parsing errors (Missing argument 'VERSION')
    # Because there is no changelog, it should exit 1 (warns no unreleased entries), but the exit code must not be click parse error (which is 2).
    assert result.exit_code == 1


# Silence unused-import warnings.
_ = subprocess
