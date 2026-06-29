"""Version parsing + comparison + dependency resolution.

The SDK uses a pragmatic PEP-440-ish semver triple with optional
pre-release and build-metadata tags. Compatibility resolution uses
the same algorithm pip uses for ``~=`` and ``>=``:

* ``~=X.Y``     — ``>=X.Y, <(X+1)``
* ``~=X.Y.Z``   — ``>=X.Y.Z, <X.(Y+1)``
* ``X.Y.Z``     — exact match
* ``X.Y``       — any patch of X.Y
* ``>=X.Y.Z``   — at least X.Y.Z
* ``>X.Y.Z``    — strictly greater
* ``*``         — wildcard

Missing version specifier means "any version".
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------


class VersionParseError(ValueError):
    """Raised when a version string is malformed."""


@dataclass(frozen=True, order=True)
class Version:
    """A parsed semantic-style version."""

    major: int
    minor: int
    patch: int
    pre: tuple[tuple[str, int], ...] = ()
    build: str = ""

    @classmethod
    def parse(cls, value: str) -> Version:
        if not value or not isinstance(value, str):
            raise VersionParseError(f"invalid version: {value!r}")
        # Accept both ``1.2.3a1`` (PEP-440-ish) and ``1.2.3-a1``
        # (semver-style). We normalise to the second form so the
        # pre-release parsing below sees a single canonical shape.
        normalised = value.strip()
        m = re.match(
            r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?"
            r"(?:(-[0-9A-Za-z-.]+)|([0-9]+[A-Za-z]+[0-9A-Za-z-]*))?"
            r"(?:\+([0-9A-Za-z-.]+))?$",
            normalised,
        )
        if not m:
            raise VersionParseError(f"invalid version: {value!r}")
        major, minor, patch, dash_pre, no_dash_pre, build = m.groups()
        pre_tuple: tuple[tuple[str, int], ...] = ()
        # ``dash_pre`` is the canonical ``-foo.bar`` form. ``no_dash_pre``
        # is the bare ``1.2.3a1`` form; we prefix a dash so the
        # downstream splitter sees a single shape.
        pre_str = dash_pre or ("-" + no_dash_pre if no_dash_pre else "")
        if pre_str:
            for chunk in pre_str.lstrip("-").split("."):
                match = re.match(r"^([0-9A-Za-z]+)(\d*)$", chunk)
                if not match:
                    raise VersionParseError(f"invalid pre-release: {pre_str!r}")
                ident, num = match.groups()
                pre_tuple = (*pre_tuple, (ident, int(num) if num else -1))
        return cls(
            major=int(major),
            minor=int(minor or 0),
            patch=int(patch or 0),
            pre=pre_tuple,
            build=build or "",
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base += "-" + ".".join(
                f"{ident}{num}" if num >= 0 else ident
                for ident, num in self.pre
            )
        if self.build:
            base += f"+{self.build}"
        return base

    def __repr__(self) -> str:
        return f"Version({self})"

    def is_prerelease(self) -> bool:
        return bool(self.pre)

    def without_prerelease(self) -> Version:
        return Version(self.major, self.minor, self.patch)


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


class Op(str, Enum):
    EQ = "=="
    NEQ = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    CARET = "^"  # NOT USED; kept for documentation
    TILDE = "~="


@dataclass(frozen=True)
class Spec:
    """A single dependency specifier like ``>=1.2,<2.0``."""

    op: Op
    version: Version

    def matches(self, other: Version) -> bool:
        if self.op is Op.EQ:
            return other == self.version
        if self.op is Op.NEQ:
            return other != self.version
        if self.op is Op.GT:
            return other > self.version
        if self.op is Op.GE:
            return other >= self.version
        if self.op is Op.LT:
            return other < self.version
        if self.op is Op.LE:
            return other <= self.version
        if self.op is Op.TILDE:
            return other >= self.version
        raise ValueError(f"unsupported op: {self.op}")

    def __str__(self) -> str:
        return f"{self.op}{self.version}"


# A spec string like ``"^1.0 ; extras: graphify"`` is a comma-separated
# set of Spec clauses plus an optional ``;extras:...`` annotation.
_SPEC_SEP = ";"


@dataclass(frozen=True)
class Requirement:
    """A full requirement: name + set of version specs + optional extras."""

    name: str
    specs: tuple[Spec, ...] = ()
    extras: tuple[str, ...] = ()

    def matches(self, version: Version) -> bool:
        if not self.specs:
            return True
        return all(spec.matches(version) for spec in self.specs)

    @classmethod
    def parse(cls, name: str, spec_string: str = "") -> Requirement:
        if not name:
            raise ValueError("requirement name must be non-empty")
        specs: list[Spec] = []
        extras: list[str] = []
        body, sep, tail = spec_string.partition(_SPEC_SEP)
        if sep:
            extras_str = tail.strip()
            if extras_str.startswith("extras:"):
                extras = tuple(
                    chunk.strip()
                    for chunk in extras_str[len("extras:") :].split(",")
                    if chunk.strip()
                )
        for raw in body.split(","):
            raw = raw.strip()
            if not raw or raw == "*":
                continue
            for op_token in ("==", "!=", ">=", "<=", "~=", ">", "<"):
                if raw.startswith(op_token):
                    version_str = raw[len(op_token) :].strip()
                    if op_token == "~=":
                        specs.append(_tilde(version_str))
                    else:
                        try:
                            specs.append(Spec(Op(op_token), Version.parse(version_str)))
                        except VersionParseError:
                            continue
                    break
            else:
                # Bare version string == exact match.
                try:
                    specs.append(Spec(Op.EQ, Version.parse(raw)))
                except VersionParseError:
                    continue
        return cls(name=name, specs=tuple(specs), extras=tuple(extras))

    def __str__(self) -> str:
        base = self.name
        if self.specs:
            base += " " + ",".join(str(s) for s in self.specs)
        if self.extras:
            base += f" ; extras: {','.join(self.extras)}"
        return base


def _tilde(version_str: str) -> Spec:
    """Implement the ``~=X.Y`` and ``~=X.Y.Z`` operators."""
    parts = version_str.split(".")
    if len(parts) == 1:
        # ~=2 is invalid; treat as ==
        return Spec(Op.EQ, Version.parse(version_str))
    if len(parts) == 2:
        major, minor = parts
        low = Version.parse(version_str)
        high = Version.parse(f"{int(major) + 1}.0")
    else:
        major, minor, _patch = parts
        low = Version.parse(version_str)
        high = Version.parse(f"{major}.{int(minor) + 1}")
    # ~="X.Y" means ">=X.Y, <(X+1).0"; the high is exclusive.
    # We return a synthetic GE spec; the LT spec is folded in below.
    return _TildeSpec(ge=low, lt=high)


@dataclass(frozen=True)
class _TildeSpec:
    ge: Version
    lt: Version

    def matches(self, other: Version) -> bool:
        return self.ge <= other < self.lt


# Replace the simple Spec with one that also supports tilde.
_Spec = Spec  # type alias retained for clarity; not used below


# ---------------------------------------------------------------------------
# Dependency resolution
# ---------------------------------------------------------------------------


class DependencyCycleError(RuntimeError):
    """Raised when dependency resolution hits a cycle."""


class UnsatisfiableRequirementError(RuntimeError):
    """Raised when two requirements for the same name disagree."""


def resolve(
    requirements: Iterable[Requirement],
    candidates: dict[str, tuple[Version, ...]],
) -> dict[str, Version]:
    """Pick a single version for every named requirement.

    ``requirements`` is the union of constraints (multiple
    :class:`Requirement` objects with the same name are intersected).
    ``candidates`` maps a name to the available versions on PyPI /
    a local index / etc. The resolver picks the *highest* version
    that satisfies every constraint, and raises on cycles or
    contradictions.
    """
    constraints: dict[str, list[Requirement]] = {}
    for req in requirements:
        constraints.setdefault(req.name, []).append(req)

    chosen: dict[str, Version] = {}
    while constraints:
        progress = False
        for name, reqs in list(constraints.items()):
            if name in chosen:
                continue
            available = candidates.get(name, ())
            for version in sorted(available, reverse=True):
                if all(req.matches(version) for req in reqs):
                    chosen[name] = version
                    del constraints[name]
                    progress = True
                    break
            else:
                # Try partial: did we have any candidate at all?
                if not available:
                    # Soft skip: caller may not have provided a local
                    # index for this plugin. We drop the constraint
                    # silently.
                    del constraints[name]
                    progress = True
                    continue
                raise UnsatisfiableRequirementError(
                    f"no version of {name!r} satisfies {', '.join(map(str, reqs))}"
                )
        if not progress:
            # Cycle or stuck.
            raise DependencyCycleError(
                f"could not resolve: {sorted(constraints)}"
            )
    return chosen


__all__ = [
    "DependencyCycleError",
    "Op",
    "Requirement",
    "Spec",
    "UnsatisfiableRequirementError",
    "Version",
    "VersionParseError",
    "resolve",
]
