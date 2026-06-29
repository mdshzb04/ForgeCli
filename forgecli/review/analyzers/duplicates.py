"""Duplicate-code detector.

A small, fast shingle-based detector that finds near-duplicate
``N``-line blocks across files in the same project. It uses a
rolling hash of normalized tokens; two blocks are considered
duplicates when they share at least ``min_match`` hashes.

This is not a full-blown clone detector; it intentionally trades
recall for speed and determinism.
"""

from __future__ import annotations

import re
import tokenize
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from io import StringIO
from typing import ClassVar

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.finding import Finding, Severity

_DEFAULT_LINE_THRESHOLD: int = 6
_DEFAULT_MIN_MATCH: int = 3


@dataclass
class DuplicatesAnalyzer(Analyzer):
    """Detect near-duplicate code blocks across files."""

    name: ClassVar[str] = "duplicates"
    category: ClassVar[str] = "duplicates"
    line_threshold: int = _DEFAULT_LINE_THRESHOLD
    min_match: int = _DEFAULT_MIN_MATCH
    max_findings: int = 50

    def run(self, context: AnalysisContext) -> list[Finding]:
        hashes: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for file in context.files:
            tokens = _tokenize_normalized(file.text)
            for index, shingle in _shingles(tokens, self.line_threshold):
                key = _hash(shingle)
                hashes[key].append((str(file.path), index + 1))

        # Coalesce occurrences: we only need to know which (file, line)
        # ranges share at least min_match shingles with another range.
        # The naive pair-of-pairs approach explodes; instead we group
        # by (file_a, file_b) and report only the first overlapping
        # range per pair.
        seen_pairs: set[tuple[str, str, int, int]] = set()
        per_pair_ranges: dict[tuple[str, str], int] = {}
        findings: list[Finding] = []

        for _key, occurrences in hashes.items():
            if len(occurrences) < 2:
                continue
            # Group occurrences into connected components where two
            # occurrences in the same file are connected if they're
            # within line_threshold of each other.
            ranges: list[tuple[str, int, int]] = []
            sorted_occ = sorted(occurrences, key=lambda o: (o[0], o[1]))
            for path, line in sorted_occ:
                if ranges and ranges[-1][0] == path and line - ranges[-1][2] < self.line_threshold:
                    start_path, start_line, _end = ranges[-1]
                    ranges[-1] = (start_path, start_line, line)
                else:
                    ranges.append((path, line, line))
            # For each (file, file) pair, count distinct overlapping ranges.
            for i in range(len(ranges)):
                for j in range(i + 1, len(ranges)):
                    a_path, a_start, _a_end = ranges[i]
                    b_path, b_start, _b_end = ranges[j]
                    if a_path == b_path:
                        continue
                    pair = (a_path, b_path)
                    if pair in per_pair_ranges and per_pair_ranges[pair] >= self.min_match:
                        continue
                    per_pair_ranges[pair] = per_pair_ranges.get(pair, 0) + 1
                    if per_pair_ranges[pair] >= self.min_match:
                        key_pair = (
                            a_path,
                            b_path,
                            min(a_start, b_start),
                            max(a_start, b_start),
                        )
                        if key_pair in seen_pairs:
                            continue
                        seen_pairs.add(key_pair)
                        if len(findings) >= self.max_findings:
                            return findings
                        findings.append(
                            Finding(
                                rule_id="DUP001",
                                category="duplicates",
                                severity=Severity.LOW,
                                message=(
                                    f"~{self.line_threshold}-line block near "
                                    f"{a_path}:{a_start} duplicates "
                                    f"{b_path}:{b_start}."
                                ),
                                path=a_path,
                                line=a_start,
                                suggestion=(
                                    "Extract the shared block into a helper."
                                ),
                                extra={
                                    "other_path": b_path,
                                    "other_line": b_start,
                                },
                            )
                        )
        return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokenize_normalized(text: str) -> list[str]:
    """Return a normalized token stream: identifiers mapped to ``id``,
    literals dropped, whitespace collapsed.
    """
    tokens: list[str] = []
    try:
        for token in tokenize.generate_tokens(StringIO(text).readline):
            if token.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                continue
            if token.type == tokenize.COMMENT:
                continue
            if token.type == tokenize.STRING or token.type == tokenize.NUMBER:
                tokens.append("lit")
            elif token.type == tokenize.NAME:
                tokens.append("id")
            else:
                tokens.append(token.string.strip())
    except (tokenize.TokenizeError, IndentationError):
        return tokens
    return [t for t in tokens if t]


def _shingles(tokens: list[str], size: int) -> Iterable[tuple[int, list[str]]]:
    """Yield ``(start_index, shingle)`` pairs of ``size`` consecutive tokens."""
    if len(tokens) < size:
        return
    for index in range(len(tokens) - size + 1):
        yield index, tokens[index : index + size]


def _hash(shingle: Iterable[str]) -> int:
    """Stable 32-bit hash for a shingle."""
    import hashlib

    payload = "\x1f".join(shingle).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=4).digest()
    return int.from_bytes(digest, "big", signed=False)


__all__ = ["DuplicatesAnalyzer"]


# Silence unused-import warnings for symbols only used in some branches.
_ = re
