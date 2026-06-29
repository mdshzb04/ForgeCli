"""Stage 4 — diff extraction.

LLMs love to wrap their output in prose. We extract the largest
unified diff block from the response (looking for ``diff --git`` or
``--- a/`` / ``+++ b/`` markers) and store the cleaned text in
``context.diff_text``. If no diff is found, ``diff_text`` is empty and
downstream stages short-circuit.
"""

from __future__ import annotations

import re

from forgecli.build import BuildContext


_GIT_DIFF_HEADER = re.compile(r"^diff --git ", re.MULTILINE)
_UNIFIED_HEADER = re.compile(r"^--- ", re.MULTILINE)
_DIFF_LINE = re.compile(r"^(?:--- |\+\+\+ |@@ | |\+|-)", re.MULTILINE)
_DIFF_OR_CONTEXT = re.compile(r"^(?:--- |\+\+\+ |@@ | |\+|-|index )", re.MULTILINE)


def extract_diff(text: str) -> str:
    """Return the largest unified-diff substring in ``text``.

    The search is anchored to the first ``diff --git`` or ``--- a/`` header
    and runs to the first non-diff-looking line that follows a blank line
    or the end of the text. We deliberately keep this lenient: real
    models emit all kinds of surrounding chatter.
    """
    if not text:
        return ""
    match = _GIT_DIFF_HEADER.search(text)
    if not match:
        match = _UNIFIED_HEADER.search(text)
    if not match:
        return ""
    candidate = text[match.start():]
    return _trim_to_diff_block(candidate)


def _trim_to_diff_block(candidate: str) -> str:
    """Trim trailing prose that is clearly not part of the diff.

    We keep the diff block intact (including context lines) and stop at
    the first blank or non-diff line that follows a substantive diff.
    """
    lines = candidate.splitlines()
    kept: list[str] = []
    for line in lines:
        if not kept and not line.strip():
            continue
        if not _DIFF_OR_CONTEXT.match(line) and not line.startswith("diff --git "):
            # We've hit prose. Stop here (but keep what we have).
            if kept:
                break
            continue
        kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def _looks_like_diff_line(line: str) -> bool:
    if _DIFF_LINE.match(line):
        return True
    if line.startswith("diff --git "):
        return True
    if line.startswith("index "):
        return True
    return False


async def diff_extraction(context: BuildContext) -> BuildContext:
    """Extract a unified diff from ``context.response`` and store in ``diff_text``."""
    if context.response is None:
        return context
    context.diff_text = extract_diff(context.response.message.content or "")
    return context


__all__ = ["diff_extraction", "extract_diff"]
