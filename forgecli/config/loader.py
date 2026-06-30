"""Load configuration from TOML files and merge with environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]

from forgecli.config.settings import ForgeSettings
from forgecli.core.errors import ConfigError


class ConfigLoader:
    """Resolve and load configuration from disk and the environment."""

    DEFAULT_CANDIDATES: tuple[Path, ...] = (
        Path("./forgecli.toml"),
        Path("./.forgecli.toml"),
        Path("./pyproject.toml"),
    )

    def __init__(self, *user_paths: Path) -> None:
        self._user_paths: tuple[Path, ...] = user_paths
        self._cached: ForgeSettings | None = None

    def load(self, *, force: bool = False) -> ForgeSettings:
        """Load the configuration, caching the result for subsequent calls."""
        if self._cached is not None and not force:
            return self._cached

        data: dict[str, Any] = {}
        for path in self._candidate_paths():
            if not path.exists():
                continue
            data = self._merge(data, self._read_toml(path))

        try:
            settings = ForgeSettings(**data)
        except Exception as exc:  # pragma: no cover - delegated validation
            raise ConfigError(f"Invalid configuration: {exc}") from exc

        self._cached = settings
        return settings

    def invalidate(self) -> None:
        """Clear the in-memory cache so the next ``load`` re-reads files."""
        self._cached = None

    def _candidate_paths(self) -> list[Path]:
        if self._user_paths:
            return list(self._user_paths)
        return list(self.DEFAULT_CANDIDATES)

    @staticmethod
    def _read_toml(path: Path) -> dict[str, Any]:
        if path.name == "pyproject.toml":
            try:
                payload = tomllib.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise ConfigError(f"Unable to read {path}: {exc}") from exc
            tool = payload.get("tool", {}).get("forgecli")
            return dict(tool) if isinstance(tool, dict) else {}

        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"Unable to read {path}: {exc}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Malformed TOML in {path}: {exc}") from exc

    @staticmethod
    def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge two dictionaries, ``override`` winning on conflict."""
        result: dict[str, Any] = dict(base)
        for key, value in override.items():
            existing = result.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                result[key] = ConfigLoader._merge(existing, value)
            else:
                result[key] = value
        return result
