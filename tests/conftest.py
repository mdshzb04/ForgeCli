"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from forgecli.config.loader import ConfigLoader
from forgecli.config.settings import ForgeSettings
from forgecli.core.container import Container
from forgecli.core.context import AppContext
from forgecli.utils.paths import ProjectPaths


@pytest.fixture
def tmp_project_paths(tmp_path: Path) -> ProjectPaths:
    """Return a :class:`ProjectPaths` rooted at a temporary directory."""
    return ProjectPaths(
        cwd=tmp_path,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        logs_dir=tmp_path / "logs",
        prompts_dir=tmp_path / "prompts",
        plugins_dir=tmp_path / "plugins",
    ).ensure()


@pytest.fixture
def container() -> Container:
    return Container()


@pytest.fixture
def app_context(tmp_project_paths: ProjectPaths) -> AppContext:
    return AppContext(paths=tmp_project_paths, loader=ConfigLoader())


@pytest.fixture
def default_settings() -> ForgeSettings:
    return ForgeSettings()


@pytest.fixture
def isolated_cwd(tmp_path: Path) -> Iterator[Path]:
    """Run a test with ``cwd`` set to a temporary directory."""
    import os

    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(previous)
