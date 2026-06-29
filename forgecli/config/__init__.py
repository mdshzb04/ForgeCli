"""Configuration loading and validation.

Public names are exposed lazily to avoid import cycles with
:mod:`forgecli.core.context`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["ConfigLoader", "ForgeSettings"]


if TYPE_CHECKING:  # pragma: no cover - typing only
    from forgecli.config.loader import ConfigLoader
    from forgecli.config.settings import ForgeSettings


def __getattr__(name: str) -> Any:
    if name == "ConfigLoader":
        from forgecli.config.loader import ConfigLoader

        return ConfigLoader
    if name == "ForgeSettings":
        from forgecli.config.settings import ForgeSettings

        return ForgeSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
