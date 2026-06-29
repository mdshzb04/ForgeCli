"""Top-level repository review.

The :class:`RepositoryReview` is the entry point used by the CLI:
load a project, run every registered analyzer, and produce a list of
:class:`Finding` objects + a ranked :class:`Suggestion` list.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from forgecli.review.analyzer import AnalysisContext, Analyzer
from forgecli.review.analyzers.architecture import ArchitectureAnalyzer
from forgecli.review.analyzers.complexity import ComplexityAnalyzer
from forgecli.review.analyzers.dead_code import DeadCodeAnalyzer
from forgecli.review.analyzers.duplicates import DuplicatesAnalyzer
from forgecli.review.analyzers.performance import PerformanceAnalyzer
from forgecli.review.analyzers.security import SecurityAnalyzer
from forgecli.review.finding import Finding, Severity
from forgecli.review.suggestions import Suggestion, build_suggestions


@dataclass
class RepositoryReview:
    """The full report produced for a single repository scan."""

    root: str
    findings: list[Finding] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    analyzer_names: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def counts_by_severity(self) -> dict[Severity, int]:
        out: dict[Severity, int] = {
            Severity.INFO: 0,
            Severity.LOW: 0,
            Severity.MEDIUM: 0,
            Severity.HIGH: 0,
            Severity.CRITICAL: 0,
        }
        for finding in self.findings:
            out[finding.severity] += 1
        return out

    def counts_by_category(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for finding in self.findings:
            out[finding.category] = out.get(finding.category, 0) + 1
        return out

    @property
    def is_blocking(self) -> bool:
        return any(finding.severity.is_blocking for finding in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "stats": self.stats,
            "analyzer_names": self.analyzer_names,
            "counts_by_severity": {
                severity.value: count
                for severity, count in self.counts_by_severity().items()
            },
            "counts_by_category": self.counts_by_category(),
            "findings": [finding.to_dict() for finding in self.findings],
            "suggestions": [
                {
                    "title": suggestion.title,
                    "severity": suggestion.severity.value,
                    "category": suggestion.category,
                    "count": suggestion.count,
                    "rationale": suggestion.rationale,
                    "findings": [finding.to_dict() for finding in suggestion.findings],
                }
                for suggestion in self.suggestions
            ],
        }


def default_analyzers() -> list[Analyzer]:
    """Return the default analyzer stack in stable order."""
    return [
        SecurityAnalyzer(),
        PerformanceAnalyzer(),
        ArchitectureAnalyzer(),
        ComplexityAnalyzer(),
        DeadCodeAnalyzer(),
        DuplicatesAnalyzer(),
    ]


def review_repository(
    root,
    *,
    analyzers: Sequence[Analyzer] | None = None,
    context: AnalysisContext | None = None,
) -> RepositoryReview:
    """Run all analyzers on ``root`` and return a :class:`RepositoryReview`."""
    analyzers = list(analyzers) if analyzers is not None else default_analyzers()
    if context is None:
        context = AnalysisContext.load(root)

    findings: list[Finding] = []
    for analyzer in analyzers:
        findings.extend(analyzer.run(context))
    suggestions = build_suggestions(findings)

    counts = {
        "files": len(context.files),
        "analyzers": len(analyzers),
    }

    return RepositoryReview(
        root=str(context.root),
        findings=findings,
        suggestions=suggestions,
        analyzer_names=[analyzer.name for analyzer in analyzers],
        stats=counts,
    )


__all__ = [
    "RepositoryReview",
    "default_analyzers",
    "review_repository",
]


# Silence unused-import warnings for symbols only used in some branches.
_ = Iterable
