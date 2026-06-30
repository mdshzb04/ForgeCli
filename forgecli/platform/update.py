"""Update check + version reporting.

ForgeCLI queries the public PyPI JSON API for the latest release
of the project and surfaces a friendly "update available" notice.

The check is:

* **Off by default.** The CLI never hits the network unless the
  user runs ``forge --check-update`` or sets
  ``FORGECLI_CHECK_UPDATE=1``.
* **Cached.** The latest version is cached in
  ``$config_dir/update.json`` for ``FORGECLI_UPDATE_CACHE_TTL``
  seconds (default 24h).
* **Quiet on failure.** Network errors return ``None`` and are
  swallowed; the CLI should still launch when offline.
* **Configurable.** ``FORGECLI_PYPI_URL`` overrides the registry
  base URL (useful for staging builds and tests).
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx

from forgecli import __version__ as _current_version
from forgecli.platform.core import getenv
from forgecli.platform.paths import data_dir, ensure_directory

DEFAULT_PYPI_URL: Final[str] = "https://pypi.org/pypi/forgecli/json"
DEFAULT_TTL_SECONDS: Final[int] = 86_400  # 24h
HTTP_TIMEOUT_SECONDS: Final[float] = 5.0
CACHE_FILENAME: Final[str] = "update.json"


@dataclass(frozen=True)
class UpdateInfo:
    """The result of a version check."""

    current: str
    latest: str | None
    update_available: bool
    checked_at: datetime
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "current": self.current,
            "latest": self.latest,
            "update_available": self.update_available,
            "checked_at": self.checked_at.isoformat(),
            "error": self.error,
        }


def current_version() -> str:
    """Return the running ForgeCLI version string."""
    return _current_version


def _cache_path() -> Path:
    """Return the path to the update cache file."""
    directory = data_dir()
    ensure_directory(directory)
    return directory / CACHE_FILENAME


def _read_cache(*, ignore_expiry: bool = False) -> dict[str, object] | None:
    """Return the cached update payload, or None if missing/expired."""
    path = _cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    checked_at = payload.get("checked_at")
    if not isinstance(checked_at, (int, float)):
        return None
    if not ignore_expiry and (time.time() - float(checked_at)) > _cache_ttl():
        return None
    return payload


def _write_cache(latest: str) -> None:
    """Write the latest version to the cache file."""
    with contextlib.suppress(OSError):
        _cache_path().write_text(
            json.dumps(
                {
                    "checked_at": time.time(),
                    "latest": latest,
                }
            ),
            encoding="utf-8",
        )


def _cache_ttl() -> int:
    raw = getenv("FORGECLI_UPDATE_CACHE_TTL")
    if raw is None:
        return DEFAULT_TTL_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def _pypi_url() -> str:
    return getenv("FORGECLI_PYPI_URL") or DEFAULT_PYPI_URL


def _parse_version(payload: dict[str, object]) -> str | None:
    """Pull the latest version string out of a PyPI JSON payload."""
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    return version if isinstance(version, str) else None


def check_for_update(
    *,
    force: bool = False,
    client_factory=None,
) -> UpdateInfo:
    """Return an :class:`UpdateInfo` for the current host.

    Reads the cache first; if the cache is fresh, returns its
    contents. Otherwise queries PyPI and updates the cache.
    """
    if not force:
        cached = _read_cache()
        if cached is not None:
            latest = cached.get("latest")
            if isinstance(latest, str):
                return _build_info(latest)

    factory = client_factory or _default_client
    try:
        with factory() as client:
            response = client.get(_pypi_url())
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        cached = _read_cache(ignore_expiry=True)
        if cached is not None:
            latest = cached.get("latest")
            if isinstance(latest, str):
                return UpdateInfo(
                    current=current_version(),
                    latest=latest,
                    update_available=_is_newer(latest, current_version()),
                    checked_at=datetime.now(UTC),
                    error=f"Offline fallback (error: {exc!r})",
                )
        return UpdateInfo(
            current=current_version(),
            latest=None,
            update_available=False,
            checked_at=datetime.now(UTC),
            error=repr(exc),
        )

    latest = _parse_version(payload) if isinstance(payload, dict) else None
    if latest is not None:
        _write_cache(latest)
    return _build_info(latest)


def _build_info(latest: str | None) -> UpdateInfo:
    """Return an :class:`UpdateInfo` for ``latest`` (may be None)."""
    current = current_version()
    update_available = latest is not None and _is_newer(latest, current)
    return UpdateInfo(
        current=current,
        latest=latest,
        update_available=update_available,
        checked_at=datetime.now(UTC),
    )


def _is_newer(latest: str, current: str) -> bool:
    """Return True when ``latest`` is a newer version than ``current``.

    Uses a simple tuple comparison on dotted-version segments. We
    don't try to handle pre-releases / post-releases specially —
    those are advisory at best and "newer" is what the user usually
    wants to see.
    """
    def _parts(version: str) -> tuple[int, ...]:
        out: list[int] = []
        for chunk in version.split("."):
            digits = ""
            for ch in chunk:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                out.append(int(digits))
            else:
                out.append(0)
        return tuple(out)

    return _parts(latest) > _parts(current)


def _default_client():
    """Return a default :class:`httpx.Client`.

    Honors the ``FORGECLI_NO_PROXY`` and ``HTTP_PROXY`` env vars;
    sets a short timeout so the check never blocks the CLI.
    """
    trust_env = bool(getenv("FORGECLI_TRUST_ENV"))
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, trust_env=trust_env)


# ---------------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------------


def should_check_on_startup() -> bool:
    """Return True if the CLI should check for updates at startup."""
    if getenv("FORGECLI_NO_UPDATE_CHECK") == "1":
        return False
    return getenv("FORGECLI_CHECK_UPDATE") == "1"


def upgrade_command() -> str:
    """Return the platform-appropriate upgrade command line."""
    return "uv tool upgrade forgecli   (or:  pip install --upgrade forgecli)"


__all__ = [
    "DEFAULT_PYPI_URL",
    "DEFAULT_TTL_SECONDS",
    "UpdateInfo",
    "check_for_update",
    "current_version",
    "should_check_on_startup",
    "upgrade_command",
]
