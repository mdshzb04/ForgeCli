"""Suggestions engine.

Turns the raw :class:`Finding` list into a ranked list of
``Suggestion`` items. The engine doesn't *fix* code; it produces a
human-readable priority order and groups findings that share a
root cause.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from forgecli.review.finding import Finding, Severity

# A small map from rule_id -> friendly title for grouping.
_RULE_TITLES: dict[str, str] = {
    "SEC001": "Hard-coded AWS access key",
    "SEC002": "Hard-coded API key/secret/password",
    "SEC003": "PEM private key in source",
    "SEC004": "Hard-coded Slack/bot token",
    "SEC010": "Avoid os.system",
    "SEC011": "Avoid os.popen",
    "SEC012": "Avoid subprocess.call (no shell=True)",
    "SEC013": "Avoid subprocess.Popen(shell=True)",
    "SEC014": "Avoid eval()",
    "SEC015": "Avoid exec()",
    "SEC016": "Avoid compile()",
    "SEC017": "Avoid pickle.load()",
    "SEC018": "Avoid pickle.loads()",
    "SEC019": "Avoid marshal.load()",
    "SEC020": "Avoid marshal.loads()",
    "SEC021": "Use a strong hash",
    "SEC022": "Don't use assert for runtime checks",
    "PERF001": "Avoid blocking I/O in async code",
    "PERF002": "Avoid sync sleep / HTTP in async code",
    "PERF010": "Deeply nested loops",
    "ARCH001": "Layer dependency direction",
    "ARCH002": "Circular import between layers",
    "ARCH003": "Forbidden import",
    "CPLX001": "Function too long",
    "CPLX002": "Function has too many parameters",
    "CPLX003": "Function has high cyclomatic complexity",
    "DEAD001": "Unused private symbol",
    "DUP001": "Duplicate code block",
}


@dataclass
class Suggestion:
    """A grouped, prioritized action item for the user."""

    title: str
    severity: Severity
    category: str
    findings: list[Finding] = field(default_factory=list)
    rationale: str = ""

    @property
    def count(self) -> int:
        return len(self.findings)


def build_suggestions(findings: Iterable[Finding]) -> list[Suggestion]:
    """Group findings by rule and rank by severity + count."""
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.rule_id].append(finding)

    suggestions: list[Suggestion] = []
    for rule_id, bucket in grouped.items():
        worst = max(bucket, key=lambda f: f.severity.weight)
        suggestions.append(
            Suggestion(
                title=_RULE_TITLES.get(rule_id, rule_id),
                severity=worst.severity,
                category=worst.category,
                findings=bucket,
                rationale=_rationale_for(rule_id, bucket),
            )
        )
    suggestions.sort(
        key=lambda s: (-s.severity.weight, -s.count, s.title),
    )
    return suggestions


def _rationale_for(rule_id: str, bucket: list[Finding]) -> str:
    """Return a short rationale for the suggestion."""
    if len(bucket) == 1:
        return f"1 occurrence of {rule_id}."
    files = {finding.path for finding in bucket if finding.path}
    file_count = len(files)
    return f"{len(bucket)} occurrences across {file_count} file(s)."


__all__ = ["Suggestion", "build_suggestions"]
