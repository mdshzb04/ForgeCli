"""Cross-platform paths, env files, and config directory resolution.

* :class:`ProjectPaths` — a typed bundle of well-known paths
  (config, data, cache, log, prompts, plugins) computed from
  environment variables with sensible XDG-style defaults via
  :mod:`platformdirs`.
* :func:`load_dotenv` — a minimal ``.env`` loader that does **not**
  overwrite existing environment variables.
* :func:`config_dir` / :func:`data_dir` / :func:`state_dir` — single
  helpers for callers that only need one path.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from forgecli.platform.core import (
    getenv,
    is_macos,
    is_windows,
)

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def _xdg_path(env_var: str, *fallback: Path) -> Path:
    """Return ``$env_var`` if set, else the first existing ``fallback``."""
    value = os.environ.get(env_var)
    if value:
        return Path(value).expanduser()
    for candidate in fallback:
        if candidate.exists():
            return candidate
    return fallback[0]


def config_dir() -> Path:
    """Return the per-user config directory for ForgeCLI.

    Honors ``FORGECLI_CONFIG_DIR`` and the platform-standard
    XDG / Apple / Windows variables (``XDG_CONFIG_HOME`` /
    ``HOME`` / ``APPDATA``). Creates the directory if missing.
    """
    if is_windows():
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif is_macos():
        base = Path.home() / "Library" / "Application Support"
    else:
        base = _xdg_path("XDG_CONFIG_HOME", Path.home() / ".config")
    path = base / "forgecli"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Return the per-user data directory for ForgeCLI."""
    override = _coerce_path("FORGECLI_DATA_DIR")
    if override is not None:
        return override
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif is_macos():
        base = Path.home() / "Library" / "Application Support"
    else:
        base = _xdg_path("XDG_DATA_HOME", Path.home() / ".local" / "share")
    path = base / "forgecli"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    """Return the per-user state directory (logs, caches)."""
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif is_macos():
        base = Path.home() / "Library" / "Application Support"
    else:
        base = _xdg_path("XDG_STATE_HOME", Path.home() / ".local" / "state")
    path = base / "forgecli"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------


def load_dotenv(
    path: Path | str | None = None,
    *,
    override: bool = False,
    encoding: str = "utf-8",
) -> dict[str, str]:
    """Load a ``.env`` file into :data:`os.environ`.

    Returns the dict of *new* (or *overridden*) variables. Existing
    environment variables are preserved unless ``override=True``.

    Comments (``#``) and blank lines are skipped. Quoted values are
    stripped; whitespace around the ``=`` is trimmed.
    """
    candidate = Path(path) if path is not None else Path.cwd() / ".env"
    if not candidate.exists():
        return {}
    try:
        text = candidate.read_text(encoding=encoding, errors="replace")
    except OSError:
        return {}

    loaded: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        # Strip a single layer of matching quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not key:
            continue
        if key in os.environ and not override:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


# ---------------------------------------------------------------------------
# ProjectPaths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectPaths:
    """All well-known filesystem locations for ForgeCLI."""

    cwd: Path
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    logs_dir: Path
    prompts_dir: Path
    plugins_dir: Path

    @classmethod
    def from_env(
        cls, *, cwd: Path | str | None = None
    ) -> ProjectPaths:
        """Resolve the default project paths for the current user.

        Environment variables take precedence: ``FORGECLI_DATA_DIR``,
        ``FORGECLI_CONFIG_DIR``, ``FORGECLI_CACHE_DIR``.
        """
        config = _coerce_path("FORGECLI_CONFIG_DIR") or config_dir()
        data = _coerce_path("FORGECLI_DATA_DIR") or data_dir()
        cache = _coerce_path("FORGECLI_CACHE_DIR") or _cache_dir()
        logs = data / "logs"
        prompts = config / "prompts"
        plugins = config / "plugins"
        for path in (config, data, cache, logs, prompts, plugins):
            path.mkdir(parents=True, exist_ok=True)
        return cls(
            cwd=Path(cwd) if cwd is not None else Path.cwd(),
            config_dir=config,
            data_dir=data,
            cache_dir=cache,
            logs_dir=logs,
            prompts_dir=prompts,
            plugins_dir=plugins,
        )


def _cache_dir() -> Path:
    """Return the cache directory, creating it if needed."""
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif is_macos():
        base = Path.home() / "Library" / "Caches"
    else:
        base = _xdg_path("XDG_CACHE_HOME", Path.home() / ".cache")
    path = base / "forgecli"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _coerce_path(env_var: str) -> Path | None:
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return None
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------


def ensure_directory(path: Path | str) -> Path:
    """Create ``path`` (and parents) if it does not exist; return it."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def merge_paths(*paths: Path | str) -> Path:
    """Return ``paths[0] / paths[1] / ... / paths[-1]`` as a :class:`Path`."""
    if not paths:
        raise ValueError("merge_paths requires at least one path")
    out = Path(paths[0])
    for tail in paths[1:]:
        out = out / tail
    return out


__all__ = [
    "ProjectPaths",
    "config_dir",
    "data_dir",
    "ensure_directory",
    "load_dotenv",
    "merge_paths",
    "state_dir",
]


# Silence the unused-import warning for the common helper.
_ = Iterable
_ = getenv
