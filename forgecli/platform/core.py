"""OS detection + small environment helpers.

All detection is a single :func:`detect_os` call, cached at module
import time, and exposed via convenient predicates (:func:`is_linux`,
:func:`is_macos`, :func:`is_windows`). The :data:`Platform` namedtuple
also exposes ``arch`` (machine type), ``release`` (kernel/OS
release), and a stable :data:`OS` enum.

This module is the *only* place that imports :mod:`sys.platform` /
:mod:`platform.machine` — everything else goes through
:func:`current_platform`.
"""

from __future__ import annotations

import os
import platform as _platform
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Final


class OS(str, Enum):
    """Stable OS identifier.

    We deliberately avoid :data:`sys.platform` strings in caller code;
    only this module reads them.
    """

    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"
    OTHER = "other"


@dataclass(frozen=True)
class Platform:
    """A snapshot of the runtime platform."""

    os: OS
    arch: str  # "x86_64" | "arm64" | "aarch64" | …
    release: str  # kernel / OS release string
    python: str  # "3.12.3"
    is_wsl: bool = False

    @property
    def is_macos(self) -> bool:
        return self.os is OS.MACOS

    @property
    def is_linux(self) -> bool:
        return self.os is OS.LINUX

    @property
    def is_windows(self) -> bool:
        return self.os is OS.WINDOWS

    @property
    def is_apple_silicon(self) -> bool:
        return self.os is OS.MACOS and self.arch == "arm64"


# A single cached snapshot taken at import time. Cheap; safe to use
# in tight loops. The call below is intentionally *after* the function
# definition so the module body executes top-to-bottom.
def _build_platform() -> Platform:
    sys_platform = sys.platform
    if sys_platform.startswith("linux"):
        os_value = OS.LINUX
    elif sys_platform == "darwin":
        os_value = OS.MACOS
    elif sys_platform in {"win32", "cygwin"}:
        os_value = OS.WINDOWS
    else:
        os_value = OS.OTHER

    arch = _platform.machine() or "unknown"
    # Normalise ARM naming on macOS.
    if os_value is OS.MACOS and arch == "aarch64":
        arch = "arm64"

    release = ""
    try:
        if os_value is OS.WINDOWS:
            release = _platform.win32_ver()[1] or _platform.release()
        elif os_value is OS.MACOS:
            release = _platform.mac_ver()[0] or _platform.release()
        else:
            release = _platform.release()
    except Exception:  # noqa: BLE001 - any failure falls back to ""
        release = ""

    is_wsl = False
    if os_value is OS.LINUX:
        try:
            with open("/proc/version", encoding="utf-8", errors="replace") as fh:
                head = fh.read(200).lower()
            is_wsl = "microsoft" in head or "wsl" in head
        except OSError:
            is_wsl = False

    return Platform(
        os=os_value,
        arch=arch,
        release=release,
        python=_platform.python_version(),
        is_wsl=is_wsl,
    )


def detect_os() -> OS:
    """Return the current :class:`OS` value.

    Equivalent to ``current_platform().os`` but slightly cheaper.
    """
    return _PLATFORM.os


def current_platform() -> Platform:
    """Return the cached :class:`Platform` snapshot."""
    return _PLATFORM


def is_windows() -> bool:
    return _PLATFORM.os is OS.WINDOWS


def is_macos() -> bool:
    return _PLATFORM.os is OS.MACOS


def is_linux() -> bool:
    return _PLATFORM.os is OS.LINUX


def python_version() -> str:
    """Return the running Python version (``'3.12.3'``)."""
    return _PLATFORM.python


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def getenv(name: str, default: str | None = None) -> str | None:
    """Read an environment variable, returning ``default`` if missing."""
    return os.environ.get(name, default)


def getenv_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Truthy: ``"1"``, ``"true"``, ``"yes"``, ``"on"`` (case-insensitive).
    Falsy: ``"0"``, ``"false"``, ``"no"``, ``"off"``, ``""``.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def getenv_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def getenv_list(name: str, default: tuple[str, ...] = (), *, sep: str = ",") -> tuple[str, ...]:
    """Parse a delimited environment variable as a tuple of strings."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(sep) if part.strip())


__all__ = [
    "OS",
    "Platform",
    "current_platform",
    "detect_os",
    "getenv",
    "getenv_bool",
    "getenv_int",
    "getenv_list",
    "is_linux",
    "is_macos",
    "is_windows",
    "python_version",
]
