"""Semantic commit analysis: diff -> structured metadata.

The :class:`CommitAnalyzer` reads the output of ``git diff`` (or any
text diff) and produces a :class:`CommitAnalysis` describing the
change in conventional-commits style: a kind, an optional scope, a
short summary, an optional body, and a list of changed files with
their inferred file kind.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CommitKind(str, Enum):
    """Conventional Commits change kind."""

    FEAT = "feat"
    FIX = "fix"
    DOCS = "docs"
    REFACTOR = "refactor"
    TEST = "test"
    CHORE = "chore"
    PERF = "perf"
    BUILD = "build"
    CI = "ci"
    STYLE = "style"

    @property
    def is_user_facing(self) -> bool:
        return self in {CommitKind.FEAT, CommitKind.FIX, CommitKind.PERF, CommitKind.DOCS}


class FileKind(str, Enum):
    """A coarse-grained kind for a single changed file."""

    SOURCE = "source"
    TEST = "test"
    DOCS = "docs"
    CONFIG = "config"
    BUILD = "build"
    CI = "ci"
    SCHEMA = "schema"
    UNKNOWN = "unknown"


# Glob patterns mapped to (kind, optional scope hint).
_KIND_RULES: list[tuple[re.Pattern[str], FileKind]] = [
    (re.compile(r"^tests?/"), FileKind.TEST),
    (re.compile(r"^(docs?|README\.md|CHANGELOG\.md|\.md$)", re.IGNORECASE), FileKind.DOCS),
    (re.compile(r"^\.github/workflows/"), FileKind.CI),
    (re.compile(r"^(Makefile|\.gitlab-ci\.yml|\.travis\.yml)"), FileKind.CI),
    (re.compile(r"^(pyproject\.toml|setup\.py|setup\.cfg|requirements.*\.txt|uv\.lock)"),
     FileKind.BUILD),
    (re.compile(r"^(\.github/|Dockerfile|docker-compose.*\.yml)$"), FileKind.CI),
    (re.compile(r"\.(json|ya?ml|toml|cfg|ini|env)$", re.IGNORECASE), FileKind.CONFIG),
    (re.compile(r"\.py$"), FileKind.SOURCE),
    (re.compile(r"\.(ts|tsx|js|jsx|go|rs|java|kt|swift|rb|c|cpp|h|hpp)$"),
     FileKind.SOURCE),
]


_SCOPE_OVERRIDES: dict[str, str] = {
    "cli": "cli",
    "core": "core",
    "config": "config",
    "memory": "memory",
    "utils": "utils",
    "prompts": "prompts",
    "templates": "templates",
    "providers": "providers",
    "graph": "graph",
    "optimizer": "optimizer",
    "planner": "planner",
    "builder": "builder",
    "review": "review",
    "git": "git",
    "build": "build",
    "tests": "tests",
    "docs": "docs",
    ".github": "ci",
    "examples": "examples",
    "scripts": "scripts",
}


# When the project source lives under a known root directory, the
# meaningful scope is the *second* path component, not the first.
_PROJECT_SOURCE_ROOTS: frozenset[str] = frozenset(
    {"forgecli", "src", "app", "pkg", "lib", "internal", "cmd"}
)


def _is_breaking(diff_text: str) -> bool:
    """Return True if the diff contains a clear breaking-change marker.

    Two signals are recognised:

    * a ``BREAKING CHANGE: …`` footer in the diff's added content.
      We require the marker to be on its own line (preceded by a blank
      line in the added block) so that literal occurrences in source
      code (e.g. error messages, docstrings) don't false-positive.
    * a ``!`` token in the type-position of a commit subject, i.e. a
      conventional-commits ``feat!: …`` or ``fix(scope)!: …`` line.
    """
    added_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])
    if _has_breaking_footer(added_lines):
        return True
    added = "\n".join(added_lines)
    return bool(_EXCLAMATION_SUBJECT.search(added))


def _has_breaking_footer(added_lines: list[str]) -> bool:
    """Return True if any line in ``added_lines`` is a breaking footer.

    A "footer" is a non-empty line that starts with the conventional
    ``BREAKING CHANGE:`` (or ``BREAKING-CHANGE:``) marker and is
    preceded by a blank line within the added block — mimicking the
    position of a commit message footer.
    """
    pattern = re.compile(r"^BREAKING[\s_-]CHANGE\s*:", re.IGNORECASE)
    prev_blank = True
    for line in added_lines:
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            continue
        if pattern.match(stripped) and prev_blank:
            return True
        prev_blank = False
    return False


@dataclass
class FileChange:
    """One row in the diff: a path plus its inferred kind and scope."""

    path: str
    kind: FileKind
    scope: str
    insertions: int = 0
    deletions: int = 0


@dataclass
class CommitAnalysis:
    """The result of analyzing a diff for a semantic commit."""

    kind: CommitKind
    scope: str | None
    summary: str
    body: str = ""
    files: list[FileChange] = field(default_factory=list)
    breaking: bool = False
    stats: dict[str, int] = field(default_factory=dict)
    rationale: tuple[str, ...] = ()

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def primary_scope(self) -> str:
        if self.scope:
            return self.scope
        if self.files:
            return self.files[0].scope
        return ""

    def file_kind_counts(self) -> dict[FileKind, int]:
        counts: Counter[FileKind] = Counter()
        for change in self.files:
            counts[change.kind] += 1
        return dict(counts)


class CommitAnalyzer:
    """Analyzes unified diffs and returns a :class:`CommitAnalysis`."""

    def analyze(self, diff_text: str) -> CommitAnalysis:
        if not diff_text or not diff_text.strip():
            return CommitAnalysis(
                kind=CommitKind.CHORE,
                scope=None,
                summary="no changes to commit",
                rationale=("diff is empty",),
            )
        files = _parse_files(diff_text)
        kind = _infer_kind(files)
        scope = _infer_scope(files)
        summary = _compose_summary(kind, scope, files)
        body = _compose_body(files, diff_text)
        breaking = _is_breaking(diff_text)
        rationale = _build_rationale(kind, scope, files, breaking)
        stats = _compute_stats(diff_text)
        return CommitAnalysis(
            kind=kind,
            scope=scope,
            summary=summary,
            body=body,
            files=files,
            breaking=breaking,
            stats=stats,
            rationale=rationale,
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


_FILE_HEADER = re.compile(r"^\+\+\+\s+(?P<path>b/.+|/dev/null)\s*$", re.MULTILINE)

# Conventional Commits "!" token: feat!:, fix(scope)!:, etc.
_EXCLAMATION_SUBJECT = re.compile(
    r"^(?:fix|feat|chore|docs|refactor|perf|test|build|ci|style)"
    r"(?:\([^)]+\))?!:",
    re.MULTILINE,
)


def _parse_files(diff_text: str) -> list[FileChange]:
    """Parse ``diff_text`` and return one :class:`FileChange` per file."""
    files: list[FileChange] = []
    for match in _FILE_HEADER.finditer(diff_text):
        path = match.group("path")
        if path == "/dev/null":
            continue
        if path.startswith("b/"):
            path = path[2:]
        block = _slice_block(diff_text, match.start())
        insertions, deletions = _count_hunk_lines(block)
        kind = _classify_file(path)
        scope = _classify_scope(path)
        files.append(
            FileChange(
                path=path,
                kind=kind,
                scope=scope,
                insertions=insertions,
                deletions=deletions,
            )
        )
    return files


def _slice_block(diff_text: str, header_start: int) -> str:
    """Return the slice of ``diff_text`` from ``header_start`` to the next
    ``+++ ``/``--- `` header (or end of text).
    """
    next_header = re.search(
        r"^(?:diff --git|Index:|\+\+\+ )", diff_text[header_start + 1 :],
        re.MULTILINE,
    )
    if next_header is None:
        return diff_text[header_start:]
    return diff_text[header_start : header_start + 1 + next_header.start()]


def _count_hunk_lines(block: str) -> tuple[int, int]:
    """Return ``(insertions, deletions)`` for one file's block."""
    insertions = 0
    deletions = 0
    for line in block.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            insertions += 1
        elif line.startswith("-"):
            deletions += 1
    return insertions, deletions


def _classify_file(path: str) -> FileKind:
    """Return the inferred :class:`FileKind` for a single file path."""
    for pattern, kind in _KIND_RULES:
        if pattern.search(path):
            return kind
    return FileKind.UNKNOWN


def _classify_scope(path: str) -> str:
    """Return the conventional-commits scope for a path.

    The scope is the top-level directory under the project. If the path
    lives under a known source root (``forgecli/``, ``src/``, etc.) we
    use the *second* component so commits inside a Python package
    produce scopes like ``graph`` rather than ``forgecli``.
    """
    parts = Path(path).parts
    if not parts:
        return ""
    head = parts[0]
    if head in _PROJECT_SOURCE_ROOTS and len(parts) > 1:
        head = parts[1]
    return _SCOPE_OVERRIDES.get(head, head)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def _infer_kind(files: list[FileChange]) -> CommitKind:
    """Pick a :class:`CommitKind` based on the mix of file kinds."""
    if not files:
        return CommitKind.CHORE
    counts = Counter(change.kind for change in files)
    if counts[FileKind.TEST] and sum(v for k, v in counts.items() if k != FileKind.TEST) == 0:
        return CommitKind.TEST
    if counts[FileKind.DOCS] and sum(v for k, v in counts.items() if k != FileKind.DOCS) == 0:
        return CommitKind.DOCS
    if counts[FileKind.CI] and sum(v for k, v in counts.items() if k != FileKind.CI) == 0:
        return CommitKind.CI
    if counts[FileKind.BUILD] and sum(v for k, v in counts.items() if k != FileKind.BUILD) == 0:
        return CommitKind.BUILD
    # Mixed source change. If the diff is dominated by removals
    # (more `-` than `+` lines) lean toward ``refactor``; otherwise
    # default to ``feat`` because the user usually wants a
    # forward-looking summary. A file with a small number of
    # replacements is treated as a fix.
    total_insertions = sum(change.insertions for change in files)
    total_deletions = sum(change.deletions for change in files)
    if total_deletions and total_deletions >= total_insertions:
        if total_deletions > total_insertions:
            return CommitKind.REFACTOR
        return CommitKind.FIX
    return CommitKind.FEAT


def _infer_scope(files: list[FileChange]) -> str | None:
    """Pick a scope for the commit; None if scopes are mixed."""
    if not files:
        return None
    scopes = {change.scope for change in files if change.scope}
    if len(scopes) == 1:
        return next(iter(scopes))
    return None


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------


_VERB_BY_KIND: dict[CommitKind, str] = {
    CommitKind.FEAT: "add",
    CommitKind.FIX: "fix",
    CommitKind.DOCS: "document",
    CommitKind.REFACTOR: "refactor",
    CommitKind.TEST: "test",
    CommitKind.CHORE: "chore",
    CommitKind.PERF: "speed up",
    CommitKind.BUILD: "build",
    CommitKind.CI: "ci",
    CommitKind.STYLE: "style",
}


_OBJECT_SINGULAR: dict[FileKind, str] = {
    FileKind.SOURCE: "module",
    FileKind.TEST: "tests",
    FileKind.DOCS: "docs",
    FileKind.CONFIG: "config",
    FileKind.BUILD: "build files",
    FileKind.CI: "CI files",
    FileKind.SCHEMA: "schema",
    FileKind.UNKNOWN: "files",
}


def _compose_summary(
    kind: CommitKind, scope: str | None, files: list[FileChange]
) -> str:
    """Return the first line of the commit message."""
    verb = _VERB_BY_KIND[kind]
    if not files:
        return f"{kind.value}: no changes"
    if len(files) == 1:
        file = files[0]
        name = Path(file.path).name or file.path
        # When the file is a source file the kind is implicit in its
        # location; drop the redundant ``(docs)``/``(test)`` suffix to
        # keep the subject tight.
        if file.kind is FileKind.SOURCE:
            return _format_summary(verb, scope, name)
        label = _OBJECT_SINGULAR[file.kind]
        return _format_summary(verb, scope, f"{name} ({label})")
    counts = Counter(change.kind for change in files)
    most_common_kind, most_common_count = counts.most_common(1)[0]
    label = _OBJECT_SINGULAR[most_common_kind]
    plural = "" if most_common_count == 1 else "s"
    return _format_summary(verb, scope, f"{most_common_count} {label}{plural}")


def _format_summary(verb: str, scope: str | None, payload: str) -> str:
    """Format ``verb(scope): payload`` honoring Conventional Commits."""
    if scope:
        return f"{verb}({scope}): {payload}"
    return f"{verb}: {payload}"


def _compose_body(files: list[FileChange], diff_text: str) -> str:
    """Return a multi-line body summarizing the file-level changes."""
    if not files:
        return ""
    # Cap body to a reasonable number of lines.
    sample = files[:12]
    lines = ["", "Files:"]
    for change in sample:
        bullet = f"- {change.path}"
        if change.insertions or change.deletions:
            bullet += f" (+{change.insertions}/-{change.deletions})"
        lines.append(bullet)
    if len(files) > len(sample):
        lines.append(f"- (+{len(files) - len(sample)} more)")
    return "\n".join(lines)


def _build_rationale(
    kind: CommitKind,
    scope: str | None,
    files: list[FileChange],
    breaking: bool,
) -> tuple[str, ...]:
    """Return a list of short human-readable reasons for the analysis."""
    reasons: list[str] = [f"kind={kind.value}"]
    if scope:
        reasons.append(f"scope={scope}")
    counts = Counter(change.kind for change in files)
    if counts:
        reason = ", ".join(f"{n} {k.value}" for k, n in sorted(counts.items()))
        reasons.append(f"files: {reason}")
    if breaking:
        reasons.append("breaking change detected")
    return tuple(reasons)


def _compute_stats(diff_text: str) -> dict[str, int]:
    """Return ``{"files", "insertions", "deletions"}`` for the diff."""
    files = 0
    insertions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            files += 1
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {"files": files, "insertions": insertions, "deletions": deletions}


__all__ = [
    "CommitAnalysis",
    "CommitAnalyzer",
    "CommitKind",
    "FileChange",
    "FileKind",
]
