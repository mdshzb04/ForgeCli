"""Resolve common filesystem locations used by ForgeCLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Bundle of well-known paths used across the application."""

    cwd: Path
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    logs_dir: Path
    prompts_dir: Path
    plugins_dir: Path

    @classmethod
    def from_env(cls, *, cwd: os.PathLike[str] | str | None = None) -> ProjectPaths:
        """Compute the default project paths using ``platformdirs`` semantics.

        ``FORGECLI_DATA_DIR`` and ``FORGECLI_CONFIG_DIR`` may be set to
        override the per-OS defaults (useful for tests and CI).
        """
        from platformdirs import PlatformDirs  # local import to keep deps light

        dirs = PlatformDirs("forgecli", appauthor=False, version=None)
        cwd_path = Path(cwd) if cwd is not None else Path.cwd()
        data_dir = Path(os.environ["FORGECLI_DATA_DIR"]) if os.environ.get("FORGECLI_DATA_DIR") else Path(dirs.user_data_dir)
        config_dir = Path(os.environ["FORGECLI_CONFIG_DIR"]) if os.environ.get("FORGECLI_CONFIG_DIR") else Path(dirs.user_config_dir)
        return cls(
            cwd=cwd_path,
            config_dir=config_dir,
            data_dir=data_dir,
            cache_dir=Path(dirs.user_cache_dir),
            logs_dir=Path(dirs.user_log_dir),
            prompts_dir=config_dir / "prompts",
            plugins_dir=config_dir / "plugins",
        )

    def ensure(self) -> ProjectPaths:
        """Create all directories in place; returns ``self`` for chaining."""
        for attr in (
            "config_dir",
            "data_dir",
            "cache_dir",
            "logs_dir",
            "prompts_dir",
            "plugins_dir",
        ):
            getattr(self, attr).mkdir(parents=True, exist_ok=True)
        return self


def to_privacy_path(p: Path | str | None) -> str:
    """Convert an absolute path to a home-relative path with ~ for privacy."""
    if p is None:
        return ""
    try:
        path_obj = Path(p).resolve()
        home = Path.home().resolve()
        if home in path_obj.parents or path_obj == home:
            return f"~/{path_obj.relative_to(home)}"
        return str(path_obj)
    except Exception:
        return str(p)
