"""Smoke tests for the configuration loader."""

from __future__ import annotations

from pathlib import Path

from forgecli.config.loader import ConfigLoader
from forgecli.config.settings import ForgeSettings


def test_loader_returns_default_settings_when_no_file(tmp_path: Path) -> None:
    loader = ConfigLoader(tmp_path / "missing.toml")
    settings = loader.load()
    assert isinstance(settings, ForgeSettings)
    assert settings.app.name == "forgecli"


def test_loader_reads_explicit_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "forgecli.toml"
    config_path.write_text(
        '[app]\nname = "myapp"\nlog_level = "DEBUG"\n',
        encoding="utf-8",
    )
    settings = ConfigLoader(config_path).load()
    assert settings.app.name == "myapp"
    assert settings.app.log_level == "DEBUG"


def test_loader_merges_pyproject_section(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.forgecli.app]\nname = "pp"\n',
        encoding="utf-8",
    )
    settings = ConfigLoader(pyproject).load()
    assert settings.app.name == "pp"
