"""Cross-platform support layer for ForgeCLI.

ForgeCLI must run identically on Windows 10/11, macOS (Intel and
Apple Silicon) and Linux (Ubuntu, Fedora, Debian, Arch, Kali,
openSUSE, etc.). This package is the *only* place where platform
detection, dependency discovery, environment handling, and shell
adaption live.

The package is split into focused modules:

* :mod:`forgecli.platform.core`     — OS detection + env helpers
* :mod:`forgecli.platform.paths`    — config / data / cache dirs
* :mod:`forgecli.platform.shell`    — shell adapter (no POSIX-only
  hardcoding)
* :mod:`forgecli.platform.deps`     — git / graphify / ponytail / python /
  node / package-manager detection
* :mod:`forgecli.platform.update`   — PyPI update check + version

Downstream code must import from this package rather than from
:mod:`sys` / :mod:`os` / :mod:`platform` directly.
"""

from forgecli.platform.core import (
    OS,
    Platform,
    current_platform,
    detect_os,
    is_linux,
    is_macos,
    is_windows,
    python_version,
)
from forgecli.platform.deps import (
    DependencyReport,
    DependencyStatus,
    check_dependencies,
    find_executable,
    has_git,
    has_graphify,
    has_node,
    has_ponytail,
    has_python,
    install_hint,
)
from forgecli.platform.paths import (
    ProjectPaths,
    config_dir,
    data_dir,
    load_dotenv,
    state_dir,
)
from forgecli.platform.shell import ShellResult, run, shell_quote
from forgecli.platform.update import (
    UpdateInfo,
    check_for_update,
    current_version,
)

__all__ = [
    "OS",
    "DependencyReport",
    "DependencyStatus",
    "Platform",
    "ProjectPaths",
    "ShellResult",
    "UpdateInfo",
    "check_dependencies",
    "check_for_update",
    "config_dir",
    "current_platform",
    "current_version",
    "data_dir",
    "detect_os",
    "find_executable",
    "has_git",
    "has_graphify",
    "has_node",
    "has_ponytail",
    "has_python",
    "install_hint",
    "is_linux",
    "is_macos",
    "is_windows",
    "load_dotenv",
    "python_version",
    "run",
    "shell_quote",
    "state_dir",
]
