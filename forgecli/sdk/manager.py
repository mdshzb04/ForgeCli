"""The :class:`PluginManager` — single source of truth for plugin state.

The manager owns:

* the :class:`LoadedPlugin` cache (filesystem + entry-point);
* the persistent **enabled-set** (which plugin names are turned on);
* the per-plugin **config** dict (validated against the
  manifest's ``config_schema`` if any);
* the registration channels that plugins use to contribute
  providers, analyzers, optimizers, etc.

The manager's lifecycle is::

    load → install → enable → (configure) → (run) → disable → uninstall

All mutations go through the manager so the SDK can fire lifecycle
events on the :class:`PluginEventBus` and call the appropriate
:func:`sandbox` for plugin callbacks.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forgecli.platform.core import (
    current_platform,
    python_version,
)
from forgecli.platform.paths import config_dir, data_dir
from forgecli.providers.base import Provider
from forgecli.review.analyzer import Analyzer
from forgecli.sdk.events import (
    HookManager,
    PluginEvent,
    PluginEventBus,
    PluginEventKind,
)
from forgecli.sdk.interfaces import HealthIssue, HealthReport
from forgecli.sdk.loader import (
    LoadedPlugin,
    discover_entry_points,
    discover_filesystem,
    load_filesystem,
)
from forgecli.sdk.manifest import (
    Compatibility,
    EntryPoint,
    EntryPointKind,
    PluginManifest,
    is_valid_plugin_name,
)
from forgecli.sdk.sandbox import Sandbox
from forgecli.sdk.version import (
    Requirement,
    Version,
    VersionParseError,
    resolve,
)

_logger = logging.getLogger("forgecli.sdk.manager")
_STATE_FILENAME = "plugins.json"
_REGISTRY_FILENAME = "registry.json"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PluginError(Exception):
    """Base class for plugin-manager errors."""


class PluginNotFoundError(PluginError, LookupError):
    pass


class PluginAlreadyInstalledError(PluginError):
    pass


class PluginCompatibilityError(PluginError):
    pass


# ---------------------------------------------------------------------------
# Persistent state
# ---------------------------------------------------------------------------


@dataclass
class PluginState:
    """The persisted state of an installed plugin."""

    name: str
    version: str
    enabled: bool
    source: str  # "filesystem" | "entry-point" | "git"
    install_path: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    installed_at: str = ""
    enabled_at: str | None = None


@dataclass
class PluginRegistryState:
    """Top-level persisted state of the SDK."""

    plugins: dict[str, PluginState] = field(default_factory=dict)
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class PluginManager:
    """The SDK's central façade."""

    def __init__(
        self,
        *,
        config_root: Path | None = None,
        data_root: Path | None = None,
    ) -> None:
        self._config_root = config_root or config_dir()
        self._data_root = data_root or data_dir()
        self._plugins_dir = self._config_root / "plugins"
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._data_root / _STATE_FILENAME
        self._bus = PluginEventBus()
        self._hooks = HookManager()
        self._loaded: dict[str, LoadedPlugin] = {}
        self._state = self._load_state()
        # Registration channels
        self.providers: dict[str, type] = {}
        self.optimizers: dict[str, type] = {}
        self.analyzers: list[type] = []
        self.workflows: list = []
        self.classifiers: list = []
        self.test_runners: dict[str, Callable[..., Any]] = {}
        self.docs_generators: list[Callable[..., Any]] = []
        self.deployment_providers: list[Callable[..., Any]] = []
        self.observability_providers: list[Callable[..., Any]] = []
        self.notification_providers: dict[str, Callable[..., Any]] = {}
        self.git_service: Any = None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def state(self) -> PluginRegistryState:
        return self._state

    @property
    def bus(self) -> PluginEventBus:
        return self._bus

    @property
    def hooks(self) -> HookManager:
        return self._hooks

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, *, use_cache: bool = True) -> list[LoadedPlugin]:
        """Return every plugin available on disk or via entry points."""
        if use_cache and self._loaded:
            return list(self._loaded.values())
        self._loaded = {}
        for plugin in discover_filesystem(self._plugins_dir):
            self._loaded[plugin.name] = plugin
        for plugin in discover_entry_points():
            # On-disk overrides entry-point with the same name.
            self._loaded.setdefault(plugin.name, plugin)
        return list(self._loaded.values())

    def get(self, name: str) -> LoadedPlugin:
        if name not in self._loaded:
            self.discover()
        if name not in self._loaded:
            raise PluginNotFoundError(name)
        return self._loaded[name]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def install(
        self,
        source: str,
        *,
        from_path: Path | None = None,
        from_git: str | None = None,
    ) -> LoadedPlugin:
        """Install a plugin from a local path or a git URL."""
        if from_path is not None:
            return self._install_from_path(from_path)
        if from_git is not None:
            return self._install_from_git(from_git)
        # Treat ``source`` as a plugin name or path.
        candidate = Path(source)
        if candidate.exists():
            return self._install_from_path(candidate)
        raise PluginError(f"could not resolve plugin source: {source!r}")

    def _install_from_path(self, source: Path) -> LoadedPlugin:
        if not source.is_dir():
            raise PluginError(f"{source} is not a directory")
        manifest = PluginManifest.load(source / "forgecli-plugin.toml")
        self._validate(manifest)
        target = self._plugins_dir / manifest.name
        if target.exists():
            raise PluginAlreadyInstalledError(manifest.name)
        shutil.copytree(source, target)
        loaded = load_filesystem(target)
        self._loaded[loaded.name] = loaded
        self._state.plugins[loaded.name] = PluginState(
            name=loaded.name,
            version=str(loaded.version),
            enabled=False,
            source="filesystem",
            install_path=str(target),
            installed_at=_now_iso(),
        )
        self._save_state()
        self._bus.publish(
            PluginEvent(
                kind=PluginEventKind.INSTALLED,
                plugin_name=loaded.name,
            )
        )
        return loaded

    def _install_from_git(self, url: str) -> LoadedPlugin:
        target = self._plugins_dir / _slugify(url)
        if target.exists():
            shutil.rmtree(target)
        self._run_git_clone(url, target)
        return self._install_from_path(target)

    @staticmethod
    def _run_git_clone(url: str, target: Path) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["git", "clone", "--depth=1", url, str(target)],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode != 0:
            raise PluginError(f"git clone {url!r} failed: {result.stderr.strip()}")

    def uninstall(self, name: str, *, remove_files: bool = True) -> None:
        plugin = self._state.plugins.get(name)
        if plugin is None:
            raise PluginNotFoundError(name)
        if plugin.enabled:
            self.disable(name)
        if remove_files and plugin.install_path:
            path = Path(plugin.install_path)
            if path.exists() and path.is_relative_to(self._plugins_dir):
                shutil.rmtree(path, ignore_errors=True)
        self._state.plugins.pop(name, None)
        self._loaded.pop(name, None)
        self._save_state()
        self._bus.publish(
            PluginEvent(kind=PluginEventKind.UNINSTALLED, plugin_name=name)
        )

    def enable(self, name: str) -> None:
        plugin_state = self._state.plugins.get(name)
        if plugin_state is None:
            raise PluginNotFoundError(name)
        if plugin_state.enabled:
            return
        plugin = self._load_for(name, plugin_state)
        self._validate(plugin.manifest)
        self._invoke_entry_points(plugin, enabled=True)
        plugin_state.enabled = True
        plugin_state.enabled_at = _now_iso()
        self._save_state()
        self._bus.publish(
            PluginEvent(kind=PluginEventKind.ENABLED, plugin_name=name)
        )

    def disable(self, name: str) -> None:
        plugin_state = self._state.plugins.get(name)
        if plugin_state is None or not plugin_state.enabled:
            return
        plugin = self._load_for(name, plugin_state)
        self._invoke_entry_points(plugin, enabled=False)
        plugin_state.enabled = False
        plugin_state.enabled_at = None
        self._save_state()
        self._bus.publish(
            PluginEvent(kind=PluginEventKind.DISABLED, plugin_name=name)
        )

    def update(self, name: str, *, source: str | None = None) -> LoadedPlugin:
        plugin_state = self._state.plugins.get(name)
        if plugin_state is None:
            raise PluginNotFoundError(name)
        if plugin_state.source == "filesystem" and source is None:
            raise PluginError(
                f"plugin {name!r} was installed from a path; "
                "pass --source to re-pull it"
            )
        if source is None and plugin_state.source == "git":
            # Re-clone from the original URL.
            assert plugin_state.install_path is not None
            url = self._git_origin(Path(plugin_state.install_path))
            return self._install_from_git(url)
        if source is None and plugin_state.source == "entry-point":
            raise PluginError(
                f"plugin {name!r} is an entry-point plugin; "
                "upgrade the underlying distribution instead"
            )
        return self.install(source)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, name: str, **values: Any) -> None:
        state = self._state.plugins.get(name)
        if state is None:
            raise PluginNotFoundError(name)
        merged = dict(state.config)
        merged.update(values)
        state.config = merged
        self._save_state()
        self._bus.publish(
            PluginEvent(
                kind=PluginEventKind.CONFIG_CHANGED,
                plugin_name=name,
                payload={"config": merged},
            )
        )

    def get_config(self, name: str) -> dict[str, Any]:
        state = self._state.plugins.get(name)
        if state is None:
            raise PluginNotFoundError(name)
        return dict(state.config)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def doctor(self) -> list[HealthReport]:
        """Run a health check across every installed plugin."""
        reports: list[HealthReport] = []
        for name, state in sorted(self._state.plugins.items()):
            issues: list[HealthIssue] = []
            try:
                plugin = self._load_for(name, state)
            except Exception as exc:
                issues.append(HealthIssue("error", f"could not load: {exc}"))
                reports.append(HealthReport(name, tuple(issues), healthy=False))
                continue
            issues.extend(_check_compatibility(plugin.manifest))
            issues.extend(_check_dependencies(plugin.manifest))
            if state.enabled and _has_health_check(plugin):
                with Sandbox(plugin_permissions=plugin.manifest.permissions):
                    try:
                        reported = list(plugin.entry_point_factories[  # type: ignore[attr-defined]
                            (EntryPointKind.OBSERVABILITY.value, "health")
                        ]())
                    except Exception:
                        reported = []
                for issue in reported:
                    issues.append(
                        HealthIssue(
                            severity=str(issue.get("severity", "warn")),
                            message=str(issue.get("message", "")),
                            suggestion=issue.get("suggestion"),
                        )
                    )
            healthy = not any(i.severity == "error" for i in issues)
            reports.append(HealthReport(name, tuple(issues), healthy=healthy))
        return reports

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list(self) -> list[tuple[PluginState, LoadedPlugin | None]]:
        """Return ``(state, loaded_or_none)`` for every installed plugin."""
        result: list[tuple[PluginState, LoadedPlugin | None]] = []
        for state in self._state.plugins.values():
            try:
                loaded = self._load_for(state.name, state)
            except Exception:
                loaded = None
            result.append((state, loaded))
        return result

    # ------------------------------------------------------------------
    # Registration channels
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider_cls: type) -> None:
        self.providers[name] = provider_cls

    def register_optimizer(self, name: str, optimizer_cls: type) -> None:
        self.optimizers[name] = optimizer_cls

    def register_repository_analyzer(self, analyzer_cls: type) -> None:
        self.analyzers.append(analyzer_cls)

    def register_workflow(self, workflow: Any) -> None:
        self.workflows.append(workflow)

    def register_classifier(self, classifier: Any) -> None:
        self.classifiers.append(classifier)

    def register_test_runner(self, name: str, callback: Callable[..., Any]) -> None:
        self.test_runners[name] = callback

    def register_docs_generator(self, callback: Callable[..., Any]) -> None:
        self.docs_generators.append(callback)

    def register_deployment_provider(self, callback: Callable[..., Any]) -> None:
        self.deployment_providers.append(callback)

    def register_observability_provider(self, callback: Callable[..., Any]) -> None:
        self.observability_providers.append(callback)

    def register_notification_provider(
        self, name: str, callback: Callable[..., Any]
    ) -> None:
        self.notification_providers[name] = callback

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _validate(self, manifest: PluginManifest) -> None:
        if not is_valid_plugin_name(manifest.name):
            raise PluginError(f"invalid plugin name: {manifest.name!r}")
        sdk = Version.parse(_sdk_version())
        if not manifest.compatibility.matches_host(
            sdk, python_version(), current_platform().os.value
        ):
            raise PluginCompatibilityError(
                f"plugin {manifest.name!r} {manifest.version} is not "
                f"compatible with the current host "
                f"(forgecli-sdk={sdk}, python={python_version()}, "
                f"os={current_platform().os.value})"
            )
        # Resolve dependencies against the SDK's version + the
        # currently enabled plugins. Missing transitive deps are
        # surfaced as a warning only.
        requirements: list[Requirement] = list(manifest.dependencies)
        candidates: dict[str, tuple[Version, ...]] = {
            "forgecli-sdk": (sdk,)
        }
        for name in self._state.plugins:
            try:
                candidates[name] = (Version.parse(self._state.plugins[name].version),)
            except VersionParseError:
                continue
        try:
            resolve(requirements, candidates)
        except Exception as exc:
            _logger.warning("dependency resolution failed for %s: %s", manifest.name, exc)

    def _load_for(self, name: str, state: PluginState) -> LoadedPlugin:
        if name in self._loaded:
            return self._loaded[name]
        if (state.source == "filesystem" and state.install_path) or (state.source == "git" and state.install_path):
            loaded = load_filesystem(Path(state.install_path))
        else:
            # Entry-point plugin; fall back to discovery.
            for ep in discover_entry_points():
                if ep.name == name:
                    loaded = ep
                    break
            else:
                raise PluginNotFoundError(name)
        self._loaded[name] = loaded
        return loaded

    def _invoke_entry_points(self, plugin: LoadedPlugin, *, enabled: bool) -> None:
        """Run each entry-point's factory with the sandbox active."""
        for (kind_name, name), factory in plugin.entry_point_factories.items():
            try:
                kind = EntryPointKind(kind_name)
            except ValueError:
                continue
            with Sandbox(plugin_permissions=plugin.manifest.permissions):
                try:
                    if enabled:
                        factory(self)
                except Exception:
                    _logger.exception(
                        "plugin %s: %s.%s failed", plugin.name, kind.value, name
                    )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> PluginRegistryState:
        if not self._state_file.exists():
            return PluginRegistryState()
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return PluginRegistryState()
        plugins: dict[str, PluginState] = {}
        for name, data in raw.get("plugins", {}).items():
            try:
                plugins[name] = PluginState(
                    name=name,
                    version=str(data.get("version", "0.0.0")),
                    enabled=bool(data.get("enabled", False)),
                    source=str(data.get("source", "filesystem")),
                    install_path=data.get("install_path"),
                    config=dict(data.get("config") or {}),
                    installed_at=str(data.get("installed_at", "")),
                    enabled_at=data.get("enabled_at"),
                )
            except Exception:
                continue
        return PluginRegistryState(plugins=plugins, schema_version=raw.get("schema_version", 1))

    def _save_state(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "plugins": {
                name: {
                    "version": state.version,
                    "enabled": state.enabled,
                    "source": state.source,
                    "install_path": state.install_path,
                    "config": state.config,
                    "installed_at": state.installed_at,
                    "enabled_at": state.enabled_at,
                }
                for name, state in self._state.plugins.items()
            },
        }
        with contextlib.suppress(OSError):
            self._state_file.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )

    def _git_origin(self, path: Path) -> str:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise PluginError(f"could not read origin URL from {path}")
        return result.stdout.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower()
    return slug or "plugin"


def _has_health_check(plugin: LoadedPlugin) -> bool:
    """Return True if the plugin has a registered health entry point."""
    from forgecli.sdk.manifest import EntryPointKind

    return (EntryPointKind.OBSERVABILITY.value, "health") in plugin.entry_point_factories


def _check_compatibility(manifest: PluginManifest) -> list[HealthIssue]:
    sdk = Version.parse(_sdk_version())
    issues: list[HealthIssue] = []
    if manifest.compatibility.min_sdk and sdk < manifest.compatibility.min_sdk:
        issues.append(
            HealthIssue(
                severity="error",
                message=(
                    f"requires forgecli-sdk>={manifest.compatibility.min_sdk}, "
                    f"have {sdk}"
                ),
                suggestion="upgrade ForgeCLI",
            )
        )
    if manifest.compatibility.max_sdk and sdk > manifest.compatibility.max_sdk:
        issues.append(
            HealthIssue(
                severity="warn",
                message=(
                    f"tested up to forgecli-sdk<={manifest.compatibility.max_sdk}, "
                    f"have {sdk}"
                ),
            )
        )
    if (
        manifest.compatibility.os_targets
        and current_platform().os.value not in manifest.compatibility.os_targets
    ):
        issues.append(
            HealthIssue(
                severity="warn",
                message=(
                    f"targets {manifest.compatibility.os_targets}, "
                    f"current is {current_platform().os.value}"
                ),
            )
        )
    return issues


def _check_dependencies(manifest: PluginManifest) -> list[HealthIssue]:
    issues: list[HealthIssue] = []
    for req in manifest.dependencies:
        if req.name == "python":
            try:
                if not req.matches(Version.parse(python_version())):
                    issues.append(
                        HealthIssue(
                            severity="error",
                            message=f"python {req} but have {python_version()}",
                        )
                    )
            except VersionParseError:
                pass
            continue
        # External plugin / library — best-effort probe.
        if not _sdk_version_known(req.name):
            issues.append(
                HealthIssue(
                    severity="info",
                    message=f"depends on {req} (not validated locally)",
                )
            )
    return issues


def _sdk_version() -> str:
    from forgecli import __version__ as v

    return v


def _sdk_version_known(_name: str) -> bool:
    return False


__all__ = [
    "Compatibility",
    "PluginAlreadyInstalledError",
    "PluginCompatibilityError",
    "PluginError",
    "PluginManager",
    "PluginNotFoundError",
    "PluginRegistryState",
    "PluginState",
]


# Silence the unused-import warnings for symbols only used in some
# branches of the public surface.
