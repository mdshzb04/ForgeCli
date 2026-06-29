"""Stage 5 — apply diff.

Parses a unified diff and applies it to disk. We use ``git apply`` when
the project is a git repository (it understands the format natively);
otherwise we fall back to a tiny built-in parser that handles the
common case (``--- a/path`` / ``+++ b/path`` hunks).
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from forgecli.build import BuildContext


_FILE_HEADER = re.compile(
    r"^---\s+(?P<old>a/(?P<old_path>.+)|/dev/null)\s*\n"
    r"\+\+\+\s+(?P<new>b/(?P<new_path>.+)|/dev/null)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class _ParsedFile:
    path: str
    new_content: str


def apply_unified_diff(diff_text: str, root: Path) -> list[Path]:
    """Apply ``diff_text`` under ``root`` and return touched paths."""
    if shutil.which("git") and _is_git_repo(root):
        return _apply_with_git(diff_text, root)
    return _apply_with_parser(diff_text, root)


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def _apply_with_git(diff_text: str, root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=str(root),
        input=diff_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git apply failed: {proc.stderr.strip()}")
    return _list_touched_via_git(root)


def _list_touched_via_git(root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [root / line for line in proc.stdout.splitlines() if line]


def _apply_with_parser(diff_text: str, root: Path) -> list[Path]:
    parsed = parse_unified_diff(diff_text)
    touched: list[Path] = []
    for entry in parsed:
        target = root / entry.path
        if not target.is_absolute():
            target = (root / entry.path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.new_content, encoding="utf-8")
        touched.append(target)
    return touched


def parse_unified_diff(diff_text: str) -> list[_ParsedFile]:
    """Parse a unified diff with the built-in parser.

    Supports the minimal subset that LLMs reliably emit: ``--- a/path`` /
    ``+++ b/path`` headers, optional ``@@`` hunks, and a body of
    context/added/removed lines. The full hunk walker is intentionally
    small: production callers should prefer ``git apply`` when available.
    """
    files: list[_ParsedFile] = []
    lines = diff_text.splitlines()
    index = 0
    while index < len(lines):
        match = _FILE_HEADER.match("\n".join(lines[index : index + 2]))
        if not match:
            index += 1
            continue
        old_path = match.group("old_path") or ""
        new_path = match.group("new_path") or old_path
        if not new_path:
            index += 2
            continue
        index += 2
        body: list[str] = []
        while index < len(lines):
            line = lines[index]
            if _FILE_HEADER.match("\n".join(lines[index : index + 2])):
                break
            if line.startswith("@@"):
                # Skip hunk headers; we apply via line-by-line copy.
                index += 1
                continue
            if line.startswith("diff --git ") or line.startswith("index "):
                index += 1
                continue
            if line.startswith("--- ") or line.startswith("+++ "):
                index += 1
                continue
            if line.startswith("+"):
                body.append(line[1:])
            elif line.startswith("-"):
                # removed lines: drop from target content
                pass
            else:
                body.append(line[1:] if line.startswith(" ") else line)
            index += 1
        files.append(_ParsedFile(path=new_path, new_content="\n".join(body) + "\n"))
    return files


async def apply_diff(context: BuildContext) -> BuildContext:
    """Apply ``context.diff_text`` under ``context.root``."""
    if not context.diff_text:
        return context
    if not context.root.exists():
        context.root.mkdir(parents=True, exist_ok=True)
    touched = await asyncio.to_thread(apply_unified_diff, context.diff_text, context.root)
    context.applied_files = touched
    return context


__all__ = ["apply_diff", "apply_unified_diff", "parse_unified_diff"]
