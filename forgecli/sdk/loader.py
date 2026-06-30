"""Plugin discovery and on-disk loading.

The SDK supports two complementary sources:

* **Filesystem-based** plugins. A directory under
  ``$config_dir/plugins/<name>`` containing
  ``forgecli-plugin.toml`` and a Python package. The loader reads
  the manifest, then imports the entry-point callables on enable.
* **Entry-point-based** plugins. A regular Python package with a
  ``[project.entry-points."forgecli.plugins"]`` table. The loader
  walks the active distribution set via :mod:`importlib.metadata`.

Both sources return a :class:`LoadedPlugin` (manifest + the
resolved entry-point callables + source path). The
:class:`PluginManager` consumes these.
"""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from forgecli.platform.paths import config_dir
from forgecli.sdk.manifest import PluginManifest
from forgecli.sdk.version import Version

_MANIFEST_FILENAME = "forgecli-plugin.toml"
_PLUGINS_DIRNAME = "plugins"
_ENTRY_POINT_GROUP = "forgecli.plugins"


@dataclass(frozen=True)
class LoadedPlugin:
    """The result of loading a single plugin from disk or PyPI."""

    manifest: PluginManifest
    entry_point_factories: dict
    """Map of (kind, name) -> configure(manager) callable.

    Each callable is invoked when the plugin is enabled; the
    callable uses the manager to register workflows, providers,
    analyzers, etc.
    """

    source: Path | None = None  # None for entry-point-only plugins

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> Version:
        return self.manifest.version


class PluginManifestNotFoundError(LookupError):
    """Raised when a plugin's manifest is missing or malformed."""


# Backward-compatible alias for the legacy name.
PluginManifestNotFound = PluginManifestNotFoundError


def default_plugins_dir() -> Path:
    """Return the directory where on-disk plugins live."""
    path = config_dir() / _PLUGINS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def discover_filesystem(root: Path | None = None) -> list[LoadedPlugin]:
    """Find every plugin under ``root`` (default: ``$config_dir/plugins``)."""
    base = root or default_plugins_dir()
    if not base.exists():
        return []
    plugins: list[LoadedPlugin] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / _MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            plugins.append(load_filesystem(child))
        except PluginManifestNotFound:
            continue
    return plugins


def load_filesystem(plugin_dir: Path) -> LoadedPlugin:
    """Load a single plugin from a directory on disk."""
    manifest_path = plugin_dir / _MANIFEST_FILENAME
    manifest = PluginManifest.load(manifest_path)
    factories = _load_entry_point_factories(manifest, plugin_dir)
    return LoadedPlugin(
        manifest=manifest,
        entry_point_factories=factories,
        source=plugin_dir,
    )


def discover_entry_points() -> list[LoadedPlugin]:
    """Find every plugin registered via the ``forgecli.plugins`` entry point group."""
    plugins: list[LoadedPlugin] = []
    try:
        entries = importlib_metadata.entry_points(group=_ENTRY_POINT_GROUP)
    except Exception:
        return plugins
    # Group by distribution to load one synthetic manifest per
    # distribution. This is a pragmatic choice that lets users ship
    # multiple plugins in a single distribution.
    by_distribution: dict[str | None, list] = {}
    for ep in entries:
        dist = getattr(ep, "dist", None)
        dist_name = dist.name if dist is not None else "unknown"
        by_distribution.setdefault(dist_name, []).append(ep)
    for dist_name, ep_list in by_distribution.items():
        try:
            plugins.append(_load_entry_point_distribution(dist_name, ep_list))
        except PluginManifestNotFound:
            continue
        except Exception:
            continue
    return plugins


def _load_entry_point_distribution(
    dist_name: str | None, entry_points: list
) -> LoadedPlugin:
    """Load a distribution's entry-points as a synthetic plugin."""
    if dist_name is None:
        raise PluginManifestNotFound("entry point has no distribution")
    try:
        dist = importlib_metadata.distribution(dist_name)
    except importlib_metadata.PackageNotFoundError as exc:
        raise PluginManifestNotFound(dist_name) from exc
    # Use the distribution's metadata to build a synthetic manifest.
    meta = dist.metadata
    name = _coerce_name(meta.get("Name") or dist_name, dist_name)
    version = _coerce_version(meta.get("Version"))
    if version is None:
        raise PluginManifestNotFound(f"{dist_name}: no version")
    summary = meta.get("Summary", "").strip()
    summary = summary.splitlines()[0] if summary else f"{name} plugin"
    manifest = PluginManifest(
        name=name,
        version=version,
        summary=summary,
        description=meta.get("Description", "") or "",
        authors=tuple(_parse_authors(meta.get("Author"))),
        license=meta.get("License", "") or "",
        homepage=meta.get("Home-page", "") or "",
    )
    factories: dict[tuple[str, str], Callable] = {}
    for ep in entry_points:
        try:
            callback = ep.load()
        except Exception:
            continue
        from forgecli.sdk.manifest import EntryPointKind as _Kind

        try:
            kind = _Kind(ep.group.replace(f"{_ENTRY_POINT_GROUP}.", ""))
        except ValueError:
            continue
        factories[(kind.value, ep.name)] = callback
    return LoadedPlugin(
        manifest=manifest,
        entry_point_factories=factories,
        source=None,
    )


def _load_entry_point_factories(
    manifest: PluginManifest, plugin_dir: Path
) -> dict:
    """Import each ``module:attr`` reference declared in the manifest."""
    factories: dict = {}
    for ep in manifest.entry_points:
        module_name, _, attr = ep.reference.partition(":")
        if not module_name or not attr:
            continue
        try:
            module = _import_module_from_dir(module_name, plugin_dir)
        except Exception:
            continue
        callback = getattr(module, attr, None)
        if not callable(callback):
            continue
        factories[(ep.kind.value, ep.name)] = callback
    return factories


def _import_module_from_dir(name: str, plugin_dir: Path) -> ModuleType:
    """Import ``name`` from a directory under ``plugin_dir``.

    We add the plugin dir to ``sys.path`` and then ``importlib.import_module``
    so the import works for both regular packages and loose modules.
    """
    if str(plugin_dir) not in sys.path:
        sys.path.insert(0, str(plugin_dir))
    return importlib.import_module(name)


def _coerce_name(value: str | None, fallback: str) -> str:
    if not value:
        return fallback.lower().replace("_", "-").replace(" ", "-")
    return value.lower().replace("_", "-")


def _coerce_version(value: str | None) -> Version | None:
    if not value:
        return None
    from forgecli.sdk.version import Version, VersionParseError

    try:
        return Version.parse(value)
    except VersionParseError:
        return None


def _parse_authors(value: str | None) -> list[str]:
    if not value:
        return []
    return [a.strip() for a in value.split(",") if a.strip()]


# Silence unused-import warnings.

__all__ = [
    "LoadedPlugin",
    "PluginManifestNotFound",
    "default_plugins_dir",
    "discover_entry_points",
    "discover_filesystem",
    "load_filesystem",
]
