"""Dependency detection + install guidance.

The :class:`DependencyReport` aggregates the status of every
optional / required external tool ForgeCLI integrates with:

* ``git``        — required (we have a ``git`` adapter regardless)
* ``python``     — the running interpreter
* ``graphify``   — optional; powers the knowledge graph
* ``ponytail``   — optional; powers the prompt optimizer
* ``node``       — optional; needed by some LLM providers
* ``pip`` / ``uv`` / ``brew`` / ``scoop`` / ``winget`` — package
  managers used to render install hints.

Each dependency is :class:`DependencyStatus` (found / missing /
version). :func:`check_dependencies` returns a report; callers can
serialize it for ``forge doctor`` output.

Install hints are platform-aware: a missing ``graphify`` on macOS
gets a ``brew install graphify`` line; on Windows, a
``winget install Graphify.Graphify`` line; on Ubuntu, an
``apt``/``snap`` line. We never suggest a Linux command when
``is_windows()`` is True.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from forgecli.platform.core import (
    OS,
    current_platform,
    is_windows,
    python_version,
)


class DependencyStatus(str, Enum):
    """The result of probing a single external tool."""

    FOUND = "found"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"  # not supported on this platform


@dataclass(frozen=True)
class Dependency:
    """One external tool that ForgeCLI may need."""

    name: str
    status: DependencyStatus
    path: str | None = None
    version: str | None = None
    required: bool = False
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "path": self.path,
            "version": self.version,
            "required": self.required,
            "note": self.note,
        }


@dataclass(frozen=True)
class DependencyReport:
    """A snapshot of every dependency ForgeCLI cares about."""

    dependencies: tuple[Dependency, ...] = field(default_factory=tuple)

    @property
    def missing(self) -> tuple[Dependency, ...]:
        return tuple(d for d in self.dependencies if d.status is DependencyStatus.MISSING)

    @property
    def missing_required(self) -> tuple[Dependency, ...]:
        return tuple(
            d for d in self.dependencies
            if d.status is DependencyStatus.MISSING and d.required
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": current_platform().os.value,
            "arch": current_platform().arch,
            "python": python_version(),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "missing": [d.name for d in self.missing],
            "missing_required": [d.name for d in self.missing_required],
        }


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def find_executable(name: str) -> str | None:
    """Return the absolute path of ``name`` if it's on PATH, else None."""
    return shutil.which(name)


def has_git() -> bool:
    return find_executable("git") is not None


def has_python() -> bool:
    """Always True (we're running inside Python), but exposed for symmetry."""
    return True


def has_graphify() -> bool:
    return find_executable("graphify") is not None


def has_ponytail() -> bool:
    return find_executable("ponytail") is not None


def has_node() -> bool:
    return find_executable("node") is not None


def has_pip() -> bool:
    return find_executable("pip") is not None or find_executable("pip3") is not None


def has_uv() -> bool:
    return find_executable("uv") is not None


def has_homebrew() -> bool:
    return find_executable("brew") is not None


def has_scoop() -> bool:
    return find_executable("scoop") is not None


def has_winget() -> bool:
    return find_executable("winget") is not None


# ---------------------------------------------------------------------------
# Version probe
# ---------------------------------------------------------------------------


def _run_version(executable: str, args: tuple[str, ...] = ("--version",)) -> str | None:
    """Run ``executable --version`` and return the captured stdout."""
    path = find_executable(executable)
    if path is None:
        return None
    try:
        completed = __import__("subprocess").run(
            [path, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, __import__("subprocess").TimeoutExpired):
        return None
    out = (completed.stdout or completed.stderr or "").strip()
    # Trim to first line; strip noise like "git version 2.39.0".
    return out.splitlines()[0] if out else None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def check_dependencies() -> DependencyReport:
    """Return a structured :class:`DependencyReport` for the current host."""
    deps: list[Dependency] = []

    deps.append(_probe_required("git", has_git, _version_for("git")))
    deps.append(_probe_required("python", has_python, lambda: python_version()))
    deps.append(_probe_optional("graphify", has_graphify, _version_for("graphify")))
    deps.append(_probe_optional("ponytail", has_ponytail, _version_for("ponytail")))
    deps.append(_probe_optional("node", has_node, _version_for("node")))
    deps.append(_probe_optional("pip", has_pip, _version_for("pip")))
    deps.append(_probe_optional("uv", has_uv, _version_for("uv")))

    # Package managers (platform-specific).
    if is_windows():
        deps.append(_probe_optional("scoop", has_scoop, _version_for("scoop")))
        deps.append(_probe_optional("winget", has_winget, _version_for("winget")))
    else:
        deps.append(_probe_optional("brew", has_homebrew, _version_for("brew")))

    return DependencyReport(dependencies=tuple(deps))


def _version_for(executable: str):
    """Return a zero-arg callable that fetches the version of ``executable``."""
    def _callable() -> str | None:
        return _run_version(executable)
    return _callable


def _probe_required(
    name: str,
    has: callable,
    version: callable,
    *,
    note: str | None = None,
) -> Dependency:
    if has():
        return Dependency(
            name=name,
            status=DependencyStatus.FOUND,
            path=find_executable(name),
            version=version(),
            required=True,
            note=note,
        )
    return Dependency(
        name=name,
        status=DependencyStatus.MISSING,
        required=True,
        note=note or "required by ForgeCLI",
    )


def _probe_optional(
    name: str,
    has: callable,
    version: callable,
    *,
    note: str | None = None,
) -> Dependency:
    if has():
        return Dependency(
            name=name,
            status=DependencyStatus.FOUND,
            path=find_executable(name),
            version=version(),
            required=False,
            note=note,
        )
    return Dependency(
        name=name,
        status=DependencyStatus.MISSING,
        required=False,
        note=note,
    )


# ---------------------------------------------------------------------------
# Install hints
# ---------------------------------------------------------------------------


_HINTS: Final[dict[str, dict[OS, tuple[str, ...]]]] = {
    "graphify": {
        OS.LINUX: (
            "uv tool install graphifyy",
            "or:  pipx install graphify",
            "or:  pip install --user graphify",
        ),
        OS.MACOS: (
            "brew install graphify",
            "or:  uv tool install graphifyy",
        ),
        OS.WINDOWS: (
            "winget install graphify",
            "or:  scoop install graphify",
            "or:  uv tool install graphifyy",
        ),
        OS.OTHER: ("uv tool install graphifyy",),
    },
    "ponytail": {
        OS.LINUX: ("uv tool install ponytail",),
        OS.MACOS: ("brew install ponytail", "or:  uv tool install ponytail"),
        OS.WINDOWS: ("scoop install ponytail", "or:  winget install ponytail"),
        OS.OTHER: ("uv tool install ponytail",),
    },
    "git": {
        OS.LINUX: (
            "sudo apt install git          (Debian / Ubuntu)",
            "sudo dnf install git          (Fedora)",
            "sudo pacman -S git            (Arch)",
            "sudo zypper install git       (openSUSE)",
        ),
        OS.MACOS: ("xcode-select --install   (or:  brew install git)"),
        OS.WINDOWS: ("winget install Git.Git", "or:  scoop install git"),
        OS.OTHER: ("install Git from your package manager",),
    },
    "node": {
        OS.LINUX: (
            "sudo apt install nodejs      (Debian / Ubuntu)",
            "or:  https://nodejs.org/en/download",
        ),
        OS.MACOS: ("brew install node", "or:  https://nodejs.org/en/download"),
        OS.WINDOWS: ("winget install OpenJS.NodeJS", "or:  scoop install nodejs"),
        OS.OTHER: ("install Node.js from https://nodejs.org",),
    },
}


def install_hint(tool: str) -> tuple[str, ...]:
    """Return the install lines for ``tool`` on the current platform."""
    key = tool.lower().strip()
    table = _HINTS.get(key, {})
    if not table:
        return (f"see the {tool} project documentation for install instructions",)
    return table.get(current_platform().os, table[OS.OTHER])


__all__ = [
    "Dependency",
    "DependencyReport",
    "DependencyStatus",
    "check_dependencies",
    "find_executable",
    "has_git",
    "has_graphify",
    "has_homebrew",
    "has_node",
    "has_pip",
    "has_ponytail",
    "has_python",
    "has_scoop",
    "has_uv",
    "has_winget",
    "install_hint",
]


# Silence the unused-import warning for ``sys`` (kept for future
# cross-platform probes).
_ = sys
