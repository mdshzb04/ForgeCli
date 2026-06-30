"""Structured plugin metadata.

A :class:`PluginManifest` is the canonical description of a plugin:
its identity (name, version), its dependencies on other plugins and
on the host, the entry points it registers, the permissions it
asks for, and the optional compatibility constraints. Manifests
are serialised as TOML on disk (next to the plugin's source) and
parsed back into the same shape.

See :file:`PLUGINS.md` for the full schema and authoring guide.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from forgecli.sdk.version import Requirement, Version, VersionParseError


class Permission(str, Enum):
    """The kinds of resources a plugin can ask to use.

    Permissions are *advisory*: the SDK tracks what each plugin
    declares, and surfaces the list in ``forge plugin doctor`` and
    in the README. The core does not currently enforce them
    sandbox-style, but the manifest is the source of truth so
    future versions can add enforcement without changing the
    manifest schema.
    """

    NETWORK = "network"  # outbound HTTP / sockets
    SUBPROCESS = "subprocess"  # spawn child processes
    FILESYSTEM = "filesystem"  # read/write outside the plugin dir
    SECRETS = "secrets"  # read env vars / credential stores
    EXEC = "exec"  # eval / exec dynamic code
    SHELL = "shell"  # shell=True subprocess invocations
    NETWORK_LISTEN = "network-listen"  # open a server socket
    LIFECYCLE = "lifecycle"  # install / enable / disable / uninstall


# Reserved entry-point groups. A plugin declares one or more of these
# in its manifest; the SDK's loader uses the values to find the
# callable to import at enable-time.
class EntryPointKind(str, Enum):
    PROVIDER = "provider"
    REPOSITORY_ANALYZER = "repository-analyzer"
    CONTEXT_OPTIMIZER = "context-optimizer"
    CODE_GENERATOR = "code-generator"
    TEST_RUNNER = "test-runner"
    GIT_PROVIDER = "git-provider"
    DOCS_GENERATOR = "docs-generator"
    DEPLOYMENT_PROVIDER = "deployment-provider"
    OBSERVABILITY = "observability"
    NOTIFICATION = "notification"


@dataclass(frozen=True)
class EntryPoint:
    """A single ``[tool.forgecli.plugins.<name>]`` entry-point declaration."""

    kind: EntryPointKind
    name: str
    reference: str  # ``"module:attr"`` or ``"package.module:attr"``

    def __str__(self) -> str:
        return f"{self.kind.value}={self.name} -> {self.reference}"


@dataclass(frozen=True)
class Compatibility:
    """The host-version range a plugin is compatible with."""

    min_sdk: Version | None = None
    max_sdk: Version | None = None
    python: str | None = None  # e.g. ">=3.12,<3.14"
    os_targets: tuple[str, ...] = ()  # e.g. ("linux", "macos", "windows")

    def matches_host(self, sdk_version: Version, python_version: str, os_name: str) -> bool:
        if self.min_sdk is not None and sdk_version < self.min_sdk:
            return False
        if self.max_sdk is not None and sdk_version > self.max_sdk:
            return False
        if self.python is not None and not _python_matches(self.python, python_version):
            return False
        return not (bool(self.os_targets) and os_name not in self.os_targets)


def _python_matches(spec: str, version: str) -> bool:
    """Tiny PEP-440-ish subset for the ``compatibility.python`` field."""
    try:
        req = Requirement.parse("python", spec)
    except ValueError:
        return True
    try:
        return req.matches(Version.parse(version))
    except VersionParseError:
        return True


@dataclass(frozen=True)
class PluginManifest:
    """The structured description of a single plugin.

    Manifests are loaded from ``<plugin>/forgecli-plugin.toml``.
    """

    name: str
    version: Version
    summary: str
    description: str = ""
    authors: tuple[str, ...] = ()
    license: str = ""
    homepage: str = ""
    repository: str = ""
    dependencies: tuple[Requirement, ...] = ()
    permissions: tuple[Permission, ...] = ()
    entry_points: tuple[EntryPoint, ...] = ()
    compatibility: Compatibility = field(default_factory=Compatibility)
    config_schema: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> PluginManifest:
        """Read ``path`` and return a :class:`PluginManifest`."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"manifest not found: {path}")
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"could not parse manifest at {path}: {exc}") from exc
        return cls._from_dict(data, source=path)

    def dump(self) -> str:
        """Serialise the manifest as TOML."""
        try:
            import tomli_w  # type: ignore[import-not-found,import-untyped]

            return tomli_w.dumps(self._to_dict())
        except ImportError:
            # Fall back to a hand-rolled minimal TOML writer. Plugins
            # typically have tomli_w installed; this is for tests.
            return _simple_toml_dump(self._to_dict())

    @classmethod
    def _from_dict(cls, data: dict[str, Any], *, source: Path | None) -> PluginManifest:
        if not isinstance(data, dict):
            raise ValueError("manifest root must be a table")
        plugin = data.get("plugin") or data
        if not isinstance(plugin, dict):
            raise ValueError("manifest must contain a [plugin] table")

        name = _required_str(plugin, "name", source)
        version_str = _required_str(plugin, "version", source)
        try:
            version = Version.parse(version_str)
        except VersionParseError as exc:
            raise ValueError(f"manifest at {source}: invalid version {version_str!r}") from exc
        summary = _required_str(plugin, "summary", source)
        description = str(plugin.get("description", ""))
        authors = tuple(_as_str_list(plugin.get("authors")))
        license_name = str(plugin.get("license", ""))
        homepage = str(plugin.get("homepage", ""))
        repository = str(plugin.get("repository", ""))

        deps = tuple(
            Requirement.parse(str(name), str(spec))
            for name, spec in (plugin.get("dependencies") or {}).items()
        )
        permissions = tuple(
            Permission(p) for p in _as_str_list(plugin.get("permissions"))
        )
        entry_points = tuple(_parse_entry_points(plugin.get("entry_points") or {}))

        comp_data = plugin.get("compatibility") or {}
        compatibility = _parse_compatibility(comp_data)

        config_schema = dict(plugin.get("config_schema") or {})

        return cls(
            name=name,
            version=version,
            summary=summary,
            description=description,
            authors=authors,
            license=license_name,
            homepage=homepage,
            repository=repository,
            dependencies=deps,
            permissions=permissions,
            entry_points=entry_points,
            compatibility=compatibility,
            config_schema=config_schema,
            source=source,
        )

    def _to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "version": str(self.version),
            "summary": self.summary,
        }
        if self.description:
            out["description"] = self.description
        if self.authors:
            out["authors"] = list(self.authors)
        if self.license:
            out["license"] = self.license
        if self.homepage:
            out["homepage"] = self.homepage
        if self.repository:
            out["repository"] = self.repository
        if self.dependencies:
            out["dependencies"] = {r.name: str(r) for r in self.dependencies}
        if self.permissions:
            out["permissions"] = [p.value for p in self.permissions]
        if self.entry_points:
            out["entry_points"] = {
                ep.kind.value: {ep.name: ep.reference} for ep in self.entry_points
            }
        comp: dict[str, Any] = {}
        if self.compatibility.min_sdk is not None:
            comp["min_sdk"] = str(self.compatibility.min_sdk)
        if self.compatibility.max_sdk is not None:
            comp["max_sdk"] = str(self.compatibility.max_sdk)
        if self.compatibility.python:
            comp["python"] = self.compatibility.python
        if self.compatibility.os_targets:
            comp["os"] = list(self.compatibility.os_targets)
        if comp:
            out["compatibility"] = comp
        if self.config_schema:
            out["config_schema"] = self.config_schema
        return {"plugin": out}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the manifest."""
        return self._to_dict()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _required_str(data: dict[str, Any], key: str, source: Path | None) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        location = f" in {source}" if source else ""
        raise ValueError(f"manifest{location}: missing required string field {key!r}")
    return value.strip()


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _parse_entry_points(data: dict[str, Any]) -> Iterable[EntryPoint]:
    for kind_name, entries in data.items():
        try:
            kind = EntryPointKind(kind_name)
        except ValueError:
            continue
        if isinstance(entries, dict):
            for name, reference in entries.items():
                yield EntryPoint(kind=kind, name=str(name), reference=str(reference))
        elif isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", ""))
                reference = str(entry.get("reference", ""))
                if name and reference:
                    yield EntryPoint(kind=kind, name=name, reference=reference)


def _parse_compatibility(data: dict[str, Any]) -> Compatibility:
    if not isinstance(data, dict):
        return Compatibility()
    min_sdk = _maybe_version(data.get("min_sdk"))
    max_sdk = _maybe_version(data.get("max_sdk"))
    python = str(data["python"]) if "python" in data else None
    os_targets = tuple(_as_str_list(data.get("os")))
    return Compatibility(
        min_sdk=min_sdk,
        max_sdk=max_sdk,
        python=python,
        os_targets=os_targets,
    )


def _maybe_version(value: Any) -> Version | None:
    if not value:
        return None
    try:
        return Version.parse(str(value))
    except VersionParseError:
        return None


# ---------------------------------------------------------------------------
# Minimal TOML dumper (fallback when tomli_w is unavailable)
# ---------------------------------------------------------------------------


def _simple_toml_dump(data: dict[str, Any]) -> str:
    """A very small TOML writer used when tomli_w is not installed.

    Supports the subset we emit: tables, dotted keys, lists, strings,
    numbers, and booleans. Not a general TOML writer; the
    ``tomli_w`` dependency is recommended for plugin authors.
    """
    out: list[str] = []
    # First, write the top-level non-table values.
    inline: list[str] = []
    tables: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            tables[key] = value
        else:
            inline.append(f"{key} = {_toml_value(value)}")
    if inline:
        out.extend(inline)
    # Then, write each sub-table.
    for name, table in tables.items():
        if out:
            out.append("")
        out.append(f"[{name}]")
        # Nested tables, dotted keys, etc.
        for key, value in table.items():
            if isinstance(value, dict):
                # Emit as a nested table.
                out.append("")
                out.append(f"[{name}.{key}]")
                for k2, v2 in value.items():
                    out.append(f"{k2} = {_toml_value(v2)}")
            else:
                out.append(f"{key} = {_toml_value(value)}")
    return "\n".join(out) + "\n"


def _toml_value(value: Any) -> str:
    """Render a single TOML scalar / list (best-effort)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Escape backslashes and double quotes.
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        # Inline table: { key = "value", key2 = 42 }
        inner = ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items())
        return f"{{ {inner} }}"
    raise ValueError(f"cannot serialise value of type {type(value).__name__}")


# ---------------------------------------------------------------------------
# Identifier helpers
# ---------------------------------------------------------------------------


_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def is_valid_plugin_name(name: str) -> bool:
    """Return True if ``name`` is a valid plugin identifier."""
    return bool(_NAME_RE.match(name))


__all__ = [
    "Compatibility",
    "EntryPoint",
    "EntryPointKind",
    "Permission",
    "PluginManifest",
    "is_valid_plugin_name",
]
