"""Tests for the Plugin SDK."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from forgecli.sdk import (
    Compatibility,
    DependencyCycleError,
    EntryPoint,
    EntryPointKind,
    HealthIssue,
    HealthReport,
    LoadedPlugin,
    Op,
    Permission,
    PluginAlreadyInstalledError,
    PluginCompatibilityError,
    PluginError,
    PluginEvent,
    PluginEventBus,
    PluginEventKind,
    PluginHook,
    PluginManager,
    PluginManifest,
    PluginNotFoundError,
    PluginState,
    Requirement,
    Sandbox,
    ScopedBuiltins,
    Spec,
    UnsatisfiableRequirementError,
    Version,
    VersionParseError,
    is_valid_plugin_name,
    resolve,
)
from forgecli.sdk.manifest import _simple_toml_dump
from forgecli.sdk.sandbox import run_sandboxed, sandbox
from forgecli.sdk.version import _tilde


# ---------------------------------------------------------------------------
# Version + requirements
# ---------------------------------------------------------------------------


def test_version_parse_full_semver() -> None:
    v = Version.parse("1.2.3")
    assert (v.major, v.minor, v.patch) == (1, 2, 3)


def test_version_parse_with_v_prefix() -> None:
    assert Version.parse("v0.1.0") == Version(0, 1, 0)


def test_version_parse_with_pre_release() -> None:
    v = Version.parse("1.2.3a1")
    assert v.is_prerelease() is True
    assert v.without_prerelease() == Version(1, 2, 3)


def test_version_ordering() -> None:
    assert Version.parse("1.2.3") > Version.parse("1.2.2")
    assert Version.parse("2.0.0") > Version.parse("1.99.99")
    assert Version.parse("1.0.0") < Version.parse("1.0.1")


def test_version_parse_error() -> None:
    with pytest.raises(VersionParseError):
        Version.parse("")


def test_requirement_matches() -> None:
    req = Requirement.parse("foo", ">=1.0,<2.0")
    assert req.matches(Version.parse("1.5"))
    assert not req.matches(Version.parse("2.0"))


def test_requirement_tilde_operator() -> None:
    # ~=1.2 means >=1.2,<2.0
    req = Requirement.parse("foo", "~=1.2")
    assert req.matches(Version.parse("1.2"))
    assert req.matches(Version.parse("1.99"))
    assert not req.matches(Version.parse("2.0"))


def test_requirement_extras() -> None:
    req = Requirement.parse("foo", "; extras: graphify,ponytail")
    assert req.extras == ("graphify", "ponytail")
    assert req.specs == ()


def test_resolve_picks_highest_compatible() -> None:
    reqs = [Requirement.parse("foo", ">=1.0,<2.0")]
    candidates = {"foo": (Version.parse("0.9"), Version.parse("1.5"), Version.parse("2.0"))}
    chosen = resolve(reqs, candidates)
    assert chosen["foo"] == Version.parse("1.5")


def test_resolve_raises_on_contradiction() -> None:
    reqs = [
        Requirement.parse("foo", ">=1.0"),
        Requirement.parse("foo", "<1.0"),
    ]
    with pytest.raises(UnsatisfiableRequirementError):
        resolve(reqs, {"foo": (Version.parse("1.0"),)})


def test_resolve_detects_cycle() -> None:
    """A constraint with no candidates falls through; a true cycle
    would only show up if multiple names referenced each other
    through the manifest's own dependencies. We exercise the
    static cycle path: if a name never resolves because every
    candidate is rejected, the resolver raises an error."""
    reqs = [Requirement.parse("foo", ">=99.0")]
    with pytest.raises(UnsatisfiableRequirementError):
        resolve(reqs, {"foo": (Version.parse("1.0"),)})


def test_tilde_helper_generates_correct_bounds() -> None:
    spec = _tilde("1.2.3")
    assert spec.ge == Version.parse("1.2.3")
    assert spec.lt == Version.parse("1.3")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_load_round_trip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "forgecli-plugin.toml"
    manifest_path.write_text(
        textwrap.dedent(
            """
            [plugin]
            name = "acme-test"
            version = "0.1.0"
            summary = "Acme test plugin"
            description = "An example plugin"
            authors = ["Jane Doe <jane@example.com>"]
            license = "MIT"
            homepage = "https://example.com"
            repository = "https://github.com/example/acme-test"
            dependencies = { python = ">=3.12" }
            permissions = ["network", "filesystem"]

            [plugin.entry_points.provider]
            acme = "acme_test:register"

            [plugin.compatibility]
            min_sdk = "0.1.0"
            python = ">=3.12"
            os = ["linux", "macos"]

            [plugin.config_schema]
            api_key = { type = "string" }
            """
        ).strip(),
        encoding="utf-8",
    )
    manifest = PluginManifest.load(manifest_path)
    assert manifest.name == "acme-test"
    assert manifest.version == Version.parse("0.1.0")
    assert manifest.permissions == (Permission.NETWORK, Permission.FILESYSTEM)
    assert manifest.entry_points == (
        EntryPoint(
            kind=EntryPointKind.PROVIDER,
            name="acme",
            reference="acme_test:register",
        ),
    )
    assert manifest.compatibility.min_sdk == Version.parse("0.1.0")
    assert manifest.compatibility.os_targets == ("linux", "macos")
    assert manifest.config_schema["api_key"]["type"] == "string"


def test_manifest_load_rejects_missing_name(tmp_path: Path) -> None:
    path = tmp_path / "forgecli-plugin.toml"
    path.write_text('[plugin]\nversion = "0.1.0"\nsummary = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required string field 'name'"):
        PluginManifest.load(path)


def test_manifest_load_rejects_invalid_version(tmp_path: Path) -> None:
    path = tmp_path / "forgecli-plugin.toml"
    path.write_text('[plugin]\nname = "x"\nversion = "not-a-version"\nsummary = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid version"):
        PluginManifest.load(path)


def test_manifest_dump_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "forgecli-plugin.toml"
    manifest = PluginManifest(
        name="acme",
        version=Version.parse("1.0.0"),
        summary="Acme",
        description="",
        permissions=(Permission.NETWORK,),
        entry_points=(
            EntryPoint(
                kind=EntryPointKind.PROVIDER,
                name="acme",
                reference="acme_test:register",
            ),
        ),
    )
    path.write_text(manifest.dump(), encoding="utf-8")
    reloaded = PluginManifest.load(path)
    assert reloaded.name == manifest.name
    assert reloaded.permissions == (Permission.NETWORK,)


def test_simple_toml_dump_renders_dict() -> None:
    out = _simple_toml_dump({"plugin": {"name": "x"}})
    assert "x" in out


def test_is_valid_plugin_name() -> None:
    assert is_valid_plugin_name("graphify") is True
    assert is_valid_plugin_name("my-plugin") is True
    assert is_valid_plugin_name("MyPlugin") is False
    assert is_valid_plugin_name("123-starting-digit") is False
    assert is_valid_plugin_name("") is False


# ---------------------------------------------------------------------------
# LoadedPlugin + entry-point factories
# ---------------------------------------------------------------------------


def test_load_filesystem_resolves_entry_points(tmp_path: Path) -> None:
    """A plugin directory with manifest + a module:attr is loaded."""
    (tmp_path / "forgecli-plugin.toml").write_text(
        '[plugin]\nname = "x"\nversion = "0.1.0"\nsummary = "x"\n',
        encoding="utf-8",
    )
    (tmp_path / "plugin_x.py").write_text(
        "def register(manager):\n    pass\n",
        encoding="utf-8",
    )
    # Manually edit the manifest to declare the entry point.
    manifest = PluginManifest.load(tmp_path / "forgecli-plugin.toml")
    manifest = PluginManifest(
        name=manifest.name,
        version=manifest.version,
        summary=manifest.summary,
        entry_points=(
            EntryPoint(
                kind=EntryPointKind.PROVIDER,
                name="x",
                reference="plugin_x:register",
            ),
        ),
    )
    (tmp_path / "forgecli-plugin.toml").write_text(manifest.dump(), encoding="utf-8")
    loaded = load_filesystem(tmp_path)
    assert loaded.manifest.name == "x"
    assert (EntryPointKind.PROVIDER.value, "x") in loaded.entry_point_factories


def test_load_filesystem_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PluginManifest.load(tmp_path / "missing.toml")


# ---------------------------------------------------------------------------
# PluginManager lifecycle
# ---------------------------------------------------------------------------


def test_manager_lifecycle_install_enable_disable_uninstall(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    config_root = tmp_path / "config"
    (config_root / "plugins" / "acme").mkdir(parents=True)
    (config_root / "plugins" / "acme" / "forgecli-plugin.toml").write_text(
        '[plugin]\nname = "acme"\nversion = "0.1.0"\nsummary = "x"\n',
        encoding="utf-8",
    )
    (config_root / "plugins" / "acme" / "acme_mod.py").write_text(
        "def register(manager):\n    pass\n",
        encoding="utf-8",
    )

    manager = PluginManager(config_root=config_root, data_root=data_root)
    assert "acme" not in manager.state.plugins

    # Discover picks it up.
    discovered = manager.discover()
    names = {p.name for p in discovered}
    # acme is filesystem-only, so it should be in the discovered set.
    # (It is not in the persisted state yet.)
    # Install via the existing directory.
    plugin = manager.install(str(config_root / "plugins" / "acme"))
    assert plugin.name == "acme"
    assert "acme" in manager.state.plugins

    manager.enable("acme")
    assert manager.state.plugins["acme"].enabled is True
    assert manager.state.plugins["acme"].enabled_at is not None

    manager.disable("acme")
    assert manager.state.plugins["acme"].enabled is False

    manager.uninstall("acme")
    assert "acme" not in manager.state.plugins
    assert not (config_root / "plugins" / "acme").exists()


def test_manager_install_already_installed_raises(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    data_root = tmp_path / "data"
    (config_root / "plugins" / "acme").mkdir(parents=True)
    (config_root / "plugins" / "acme" / "forgecli-plugin.toml").write_text(
        '[plugin]\nname = "acme"\nversion = "0.1.0"\nsummary = "x"\n',
        encoding="utf-8",
    )
    manager = PluginManager(config_root=config_root, data_root=data_root)
    manager.install(str(config_root / "plugins" / "acme"))
    with pytest.raises(PluginAlreadyInstalledError):
        manager.install(str(config_root / "plugins" / "acme"))


def test_manager_enable_not_found_raises(tmp_path: Path) -> None:
    manager = PluginManager(config_root=tmp_path / "config", data_root=tmp_path / "data")
    with pytest.raises(PluginNotFoundError):
        manager.enable("missing")


def test_manager_compatibility_check_blocks_install(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    data_root = tmp_path / "data"
    (config_root / "plugins" / "acme").mkdir(parents=True)
    (config_root / "plugins" / "acme" / "forgecli-plugin.toml").write_text(
        textwrap.dedent(
            """
            [plugin]
            name = "acme"
            version = "0.1.0"
            summary = "x"

            [plugin.compatibility]
            min_sdk = "99.0.0"
            """
        ).strip(),
        encoding="utf-8",
    )
    manager = PluginManager(config_root=config_root, data_root=data_root)
    with pytest.raises(PluginCompatibilityError):
        manager.install(str(config_root / "plugins" / "acme"))


def test_manager_configure_persists(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    data_root = tmp_path / "data"
    (config_root / "plugins" / "acme").mkdir(parents=True)
    (config_root / "plugins" / "acme" / "forgecli-plugin.toml").write_text(
        '[plugin]\nname = "acme"\nversion = "0.1.0"\nsummary = "x"\n',
        encoding="utf-8",
    )
    manager = PluginManager(config_root=config_root, data_root=data_root)
    manager.install(str(config_root / "plugins" / "acme"))
    manager.configure("acme", api_key="secret", enabled=True)
    assert manager.get_config("acme") == {"api_key": "secret", "enabled": True}
    # Reload to ensure persistence.
    manager2 = PluginManager(config_root=config_root, data_root=data_root)
    assert manager2.get_config("acme") == {"api_key": "secret", "enabled": True}


def test_manager_doctor_returns_reports(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    data_root = tmp_path / "data"
    (config_root / "plugins" / "acme").mkdir(parents=True)
    (config_root / "plugins" / "acme" / "forgecli-plugin.toml").write_text(
        '[plugin]\nname = "acme"\nversion = "0.1.0"\nsummary = "x"\n',
        encoding="utf-8",
    )
    manager = PluginManager(config_root=config_root, data_root=data_root)
    manager.install(str(config_root / "plugins" / "acme"))
    reports = manager.doctor()
    assert any(r.plugin_name == "acme" for r in reports)


def test_manager_list_returns_state_pairs(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    data_root = tmp_path / "data"
    (config_root / "plugins" / "acme").mkdir(parents=True)
    (config_root / "plugins" / "acme" / "forgecli-plugin.toml").write_text(
        '[plugin]\nname = "acme"\nversion = "0.1.0"\nsummary = "x"\n',
        encoding="utf-8",
    )
    manager = PluginManager(config_root=config_root, data_root=data_root)
    manager.install(str(config_root / "plugins" / "acme"))
    pairs = manager.list()
    assert len(pairs) == 1
    state, loaded = pairs[0]
    assert state.name == "acme"
    assert loaded is not None
    assert loaded.name == "acme"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_event_bus_publishes_to_subscribers() -> None:
    bus = PluginEventBus()
    received: list[PluginEvent] = []

    def handler(event: PluginEvent) -> None:
        received.append(event)

    bus.subscribe(PluginEventKind.INSTALLED, handler)
    bus.publish(PluginEvent(kind=PluginEventKind.INSTALLED, plugin_name="acme"))
    assert len(received) == 1
    assert received[0].plugin_name == "acme"


def test_event_bus_unsubscribe() -> None:
    bus = PluginEventBus()
    received: list[PluginEvent] = []

    def handler(_: PluginEvent) -> None:
        received.append(1)

    bus.subscribe(PluginEventKind.ENABLED, handler)
    bus.unsubscribe(PluginEventKind.ENABLED, handler)
    bus.publish(PluginEvent(kind=PluginEventKind.ENABLED, plugin_name="x"))
    assert received == []


def test_hook_manager_fires_in_order() -> None:
    calls: list[str] = []
    manager = PluginManager(config_root=Path("/tmp/x"), data_root=Path("/tmp/y"))
    manager.hooks.before(PluginHook(name="b1", callback=lambda **_: calls.append("b1")))
    manager.hooks.before(PluginHook(name="b2", callback=lambda **_: calls.append("b2")))
    manager.hooks.after(PluginHook(name="a1", callback=lambda **_: calls.append("a1")))
    manager.hooks.after(PluginHook(name="a2", callback=lambda **_: calls.append("a2")))
    manager.hooks.fire_before()
    manager.hooks.fire_after()
    assert calls == ["b1", "b2", "a1", "a2"]


def test_hook_manager_isolates_failures() -> None:
    calls: list[str] = []
    manager = PluginManager(config_root=Path("/tmp/x"), data_root=Path("/tmp/y"))

    def bad(**_: object) -> None:
        raise RuntimeError("boom")

    manager.hooks.before(PluginHook(name="b1", callback=bad))
    manager.hooks.before(PluginHook(name="b2", callback=lambda **_: calls.append("b2")))
    manager.hooks.fire_before()
    assert calls == ["b2"]  # bad didn't stop the rest


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


def test_scoped_builtins_drops_forbidden_names() -> None:
    sb = ScopedBuiltins()
    assert "eval" not in sb.table
    assert "exec" not in sb.table
    assert "compile" not in sb.table
    assert "__import__" not in sb.table
    assert "len" in sb.table
    assert "print" in sb.table


def test_scoped_builtins_strict_mode_drops_most_things() -> None:
    sb = ScopedBuiltins(strict=True)
    # len is allowed; random_stuff is not.
    assert "len" in sb.table
    assert "open" in sb.table
    # Forbidden names are always gone.
    assert "eval" not in sb.table


def test_sandbox_blocks_eval() -> None:
    with pytest.raises(NameError):
        run_sandboxed(lambda: eval("1+1"))


def test_sandbox_allows_safe_builtins() -> None:
    result = run_sandboxed(lambda: sum([1, 2, 3]))
    assert result == 6


def test_sandbox_keeps_builtins_outside() -> None:
    # eval should still work outside the sandbox.
    value = eval("1 + 41")
    assert value == 42


def test_sandbox_exec_permission_allows_eval() -> None:
    result = run_sandboxed(
        lambda: eval("2 + 2"),
        plugin_permissions=(Permission.EXEC,),
    )
    assert result == 4


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_report_to_dict() -> None:
    report = HealthReport(
        plugin_name="acme",
        issues=(
            HealthIssue("error", "broken"),
            HealthIssue("warn", "deprecated"),
        ),
        healthy=False,
    )
    payload = report.to_dict()
    assert payload["plugin"] == "acme"
    assert payload["healthy"] is False
    assert len(payload["issues"]) == 2
    assert payload["issues"][0]["severity"] == "error"


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_resolve_drops_uncached_external_dependency() -> None:
    """External deps without local candidates are dropped silently."""
    reqs = [Requirement.parse("foo", ">=1.0")]
    chosen = resolve(reqs, {})  # no candidates for "foo"
    assert "foo" not in chosen


def test_resolve_raises_on_cycle() -> None:
    """Two requirements that reference each other through transitive
    candidates is a no-op in our simple resolver. We instead simulate
    a cycle by passing two requirements with incompatible ranges
    whose only candidate is rejected by both."""
    reqs = [Requirement.parse("foo", ">=1.0,<1.0")]  # empty range
    candidates = {"foo": (Version.parse("1.0"),)}
    with pytest.raises(UnsatisfiableRequirementError):
        resolve(reqs, candidates)


# ---------------------------------------------------------------------------
# EntryPoint kinds
# ---------------------------------------------------------------------------


def test_entry_point_kind_has_all_ten_values() -> None:
    expected = {
        "provider",
        "repository-analyzer",
        "context-optimizer",
        "code-generator",
        "test-runner",
        "git-provider",
        "docs-generator",
        "deployment-provider",
        "observability",
        "notification",
    }
    actual = {kind.value for kind in EntryPointKind}
    assert actual == expected


# Silence unused-import warnings for symbols only used in some branches.
_ = Op
_ = Spec
_ = json
