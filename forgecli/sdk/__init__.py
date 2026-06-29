"""The ForgeCLI Plugin SDK.

The SDK is the *contract* third-party developers use to extend
ForgeCLI. It provides:

* :mod:`forgecli.sdk.manifest`  — typed plugin metadata (TOML).
* :mod:`forgecli.sdk.version`    — semver parsing + dep resolution.
* :mod:`forgecli.sdk.loader`     — discovery (filesystem + entry-point).
* :mod:`forgecli.sdk.events`     — pub/sub bus + hook manager.
* :mod:`forgecli.sdk.sandbox`    — restricted-exec for plugin callbacks.
* :mod:`forgecli.sdk.interfaces` — the 10 canonical plugin types.
* :mod:`forgecli.sdk.manager`    — the :class:`PluginManager` façade
  (install / enable / disable / uninstall / update / configure).

See :file:`PLUGINS.md` for the end-to-end developer guide.
"""

from forgecli.sdk.events import (
    HookManager,
    PluginEvent,
    PluginEventBus,
    PluginEventKind,
    PluginHook,
)
from forgecli.sdk.interfaces import (
    AIProviderPlugin,
    CodeGeneratorPlugin,
    ContextOptimizerPlugin,
    DeploymentProviderPlugin,
    DocumentationGeneratorPlugin,
    GitProviderPlugin,
    HealthIssue,
    HealthReport,
    NotificationProviderPlugin,
    ObservabilityProviderPlugin,
    PluginConfigurable,
    PluginHealthCheck,
    RepositoryAnalyzerPlugin,
    TestRunnerPlugin,
)
from forgecli.sdk.loader import (
    LoadedPlugin,
    PluginManifestNotFoundError as PluginManifestNotFound,
    default_plugins_dir,
    discover_entry_points,
    discover_filesystem,
    load_filesystem,
)
from forgecli.sdk.manager import (
    PluginAlreadyInstalledError,
    PluginCompatibilityError,
    PluginError,
    PluginManager,
    PluginNotFoundError,
    PluginRegistryState,
    PluginState,
)
from forgecli.sdk.manifest import (
    Compatibility,
    EntryPoint,
    EntryPointKind,
    Permission,
    PluginManifest,
    is_valid_plugin_name,
)
from forgecli.sdk.sandbox import Sandbox, ScopedBuiltins, run_sandboxed, sandbox
from forgecli.sdk.version import (
    DependencyCycleError,
    Op,
    Requirement,
    Spec,
    UnsatisfiableRequirementError,
    Version,
    VersionParseError,
    resolve,
)

__all__ = [
    "AIProviderPlugin",
    "CodeGeneratorPlugin",
    "Compatibility",
    "ContextOptimizerPlugin",
    "DependencyCycleError",
    "DeploymentProviderPlugin",
    "DocumentationGeneratorPlugin",
    "EntryPoint",
    "EntryPointKind",
    "GitProviderPlugin",
    "HealthIssue",
    "HealthReport",
    "HookManager",
    "LoadedPlugin",
    "NotificationProviderPlugin",
    "ObservabilityProviderPlugin",
    "Op",
    "Permission",
    "PluginAlreadyInstalledError",
    "PluginCompatibilityError",
    "PluginConfigurable",
    "PluginError",
    "PluginEvent",
    "PluginEventBus",
    "PluginEventKind",
    "PluginHealthCheck",
    "PluginHook",
    "PluginManager",
    "PluginManifest",
    "PluginManifestNotFound",
    "PluginManifestNotFoundError",
    "PluginNotFoundError",
    "PluginRegistryState",
    "PluginState",
    "RepositoryAnalyzerPlugin",
    "Requirement",
    "Sandbox",
    "ScopedBuiltins",
    "Spec",
    "TestRunnerPlugin",
    "UnsatisfiableRequirementError",
    "Version",
    "VersionParseError",
    "default_plugins_dir",
    "discover_entry_points",
    "discover_filesystem",
    "is_valid_plugin_name",
    "load_filesystem",
    "resolve",
    "run_sandboxed",
    "sandbox",
]
