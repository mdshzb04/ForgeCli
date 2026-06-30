"""Tests for the review analyzer layer."""

from __future__ import annotations

import textwrap
from pathlib import Path

from forgecli.review import (
    AnalysisContext,
    Finding,
    Severity,
    build_suggestions,
    review_repository,
)
from forgecli.review.analyzers.architecture import ArchitectureAnalyzer
from forgecli.review.analyzers.complexity import ComplexityAnalyzer
from forgecli.review.analyzers.dead_code import DeadCodeAnalyzer
from forgecli.review.analyzers.duplicates import DuplicatesAnalyzer
from forgecli.review.analyzers.performance import PerformanceAnalyzer
from forgecli.review.analyzers.security import SecurityAnalyzer
from forgecli.review.report import review_to_json, review_to_markdown
from forgecli.review.repository import default_analyzers
from forgecli.review.suggestions import Suggestion


def _ctx(files: dict[str, str]) -> AnalysisContext:
    """Build an AnalysisContext from ``{relpath: text}`` mapping."""
    root = Path("/tmp/proj")
    src_files = []
    for rel, text in files.items():
        path = root / "forgecli" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        src_files.append(path)
    return AnalysisContext.load(root / "forgecli")


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def test_security_detects_hard_coded_aws_key() -> None:
    ctx = _ctx({"x.py": 'AWS = "AKIAABCDEFGHIJKLMNOP"\n'})
    findings = SecurityAnalyzer().run(ctx)
    aws = [f for f in findings if f.rule_id == "SEC001"]
    assert aws and aws[0].severity is Severity.CRITICAL


def test_security_detects_pickle_load() -> None:
    ctx = _ctx({"x.py": "import pickle\npickle.load(f)\n"})
    findings = SecurityAnalyzer().run(ctx)
    rules = {f.rule_id for f in findings}
    assert "SEC017" in rules


def test_security_detects_unsafe_subprocess_shell_true() -> None:
    ctx = _ctx({"x.py": "import subprocess\nsubprocess.Popen(cmd, shell=True)\n"})
    findings = SecurityAnalyzer().run(ctx)
    shell_findings = [f for f in findings if f.rule_id == "SEC013"]
    assert shell_findings
    # Any shell=True subprocess call is critical (command-injection vector).
    assert any(f.severity is Severity.CRITICAL for f in shell_findings)


def test_security_detects_eval() -> None:
    ctx = _ctx({"x.py": "eval('1+1')\n"})
    findings = SecurityAnalyzer().run(ctx)
    assert any(f.rule_id == "SEC014" for f in findings)


def test_security_detects_assert_in_module() -> None:
    ctx = _ctx({"x.py": "def f(x):\n    assert x > 0\n"})
    findings = SecurityAnalyzer().run(ctx)
    assert any(f.rule_id == "SEC022" for f in findings)


def test_security_detects_weak_hash() -> None:
    ctx = _ctx({"x.py": "import hashlib\nhashlib.md5(b'x')\n"})
    findings = SecurityAnalyzer().run(ctx)
    assert any(f.rule_id == "SEC021" for f in findings)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_performance_detects_blocking_io_in_async() -> None:
    ctx = _ctx(
        {
            "x.py": textwrap.dedent(
                """
                async def fetch():
                    with open('foo') as f:
                        return f.read()
                """
            ).strip()
        }
    )
    findings = PerformanceAnalyzer().run(ctx)
    assert any(f.rule_id == "PERF001" for f in findings)


def test_performance_detects_time_sleep_in_async() -> None:
    ctx = _ctx(
        {
            "x.py": textwrap.dedent(
                """
                import time
                async def fetch():
                    time.sleep(1)
                """
            ).strip()
        }
    )
    findings = PerformanceAnalyzer().run(ctx)
    assert any(f.rule_id == "PERF002" for f in findings)


def test_performance_detects_nested_loops() -> None:
    src = textwrap.dedent(
        """
        def f(matrix):
            for row in matrix:
                for cell in row:
                    for x in cell:
                        print(x)
        """
    ).strip()
    ctx = _ctx({"x.py": src})
    findings = PerformanceAnalyzer().run(ctx)
    assert any(f.rule_id == "PERF010" for f in findings)


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def test_architecture_detects_layer_violation() -> None:
    # core tries to import graph.
    ctx = _ctx({"core/x.py": "from forgecli.graph.repo import a\n"})
    findings = ArchitectureAnalyzer().run(ctx)
    assert any(f.rule_id == "ARCH001" for f in findings)


def test_architecture_detects_circular_import() -> None:
    ctx = _ctx(
        {
            "core/a.py": "from forgecli.utils.b import x\n",
            "utils/b.py": "from forgecli.core.a import y\n",
        }
    )
    findings = ArchitectureAnalyzer().run(ctx)
    assert any(f.rule_id == "ARCH002" for f in findings)


def test_architecture_forbidden_imports() -> None:
    analyzer = ArchitectureAnalyzer(forbidden_imports=("subprocess",))
    ctx = _ctx({"x.py": "import subprocess\nsubprocess.run(['ls'])\n"})
    findings = analyzer.run(ctx)
    assert any(f.rule_id == "ARCH003" for f in findings)


# ---------------------------------------------------------------------------
# Complexity
# ---------------------------------------------------------------------------


def test_complexity_detects_long_function() -> None:
    body = "\n".join("    x = 1" for _ in range(50))
    src = f"def f():\n{body}\n"
    ctx = _ctx({"x.py": src})
    findings = ComplexityAnalyzer(max_function_lines=20).run(ctx)
    assert any(f.rule_id == "CPLX001" for f in findings)


def test_complexity_detects_many_parameters() -> None:
    src = "def f(a, b, c, d, e, f, g):\n    return 1\n"
    ctx = _ctx({"x.py": src})
    findings = ComplexityAnalyzer(max_parameters=5).run(ctx)
    assert any(f.rule_id == "CPLX002" for f in findings)


def test_complexity_detects_high_cyclomatic() -> None:
    src = textwrap.dedent(
        """
        def f(x):
            if x > 0:
                return 1
            elif x > 1:
                return 2
            elif x > 2:
                return 3
            elif x > 3:
                return 4
            elif x > 4:
                return 5
            elif x > 5:
                return 6
            elif x > 6:
                return 7
            elif x > 7:
                return 8
            elif x > 8:
                return 9
            elif x > 9:
                return 10
            elif x > 10:
                return 11
            elif x > 11:
                return 12
            elif x > 12:
                return 13
            elif x > 13:
                return 14
            else:
                return 0
        """
    ).strip()
    ctx = _ctx({"x.py": src})
    findings = ComplexityAnalyzer(max_cyclomatic=5).run(ctx)
    assert any(f.rule_id == "CPLX003" for f in findings)


# ---------------------------------------------------------------------------
# Dead code
# ---------------------------------------------------------------------------


def test_dead_code_detects_unused_private(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "mod.py").write_text(
        "def _internal():\n    return 1\n\ndef public():\n    return 2\n"
    )
    ctx = AnalysisContext.load(project / "forgecli")
    findings = DeadCodeAnalyzer().run(ctx)
    rules = {f.rule_id for f in findings}
    assert "DEAD001" in rules
    # The public function should not be flagged.
    messages = [f.message for f in findings]
    assert any("_internal" in m for m in messages)
    assert not any("public" in m for m in messages)


def test_dead_code_keeps_dunder_names(tmp_path: Path) -> None:
    project = tmp_path / "proj_dead"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "mod.py").write_text(
        "class C:\n    def __repr__(self):\n        return 'C'\n"
    )
    ctx = AnalysisContext.load(project / "forgecli")
    findings = DeadCodeAnalyzer().run(ctx)
    assert not findings


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def test_duplicates_detects_repeated_block(tmp_path: Path) -> None:
    project = tmp_path / "proj_dup"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    block = textwrap.dedent(
        """
        def big_function(x):
            a = x + 1
            b = x + 2
            c = x + 3
            d = x + 4
            e = x + 5
            f = x + 6
            g = x + 7
            return a + b + c + d + e + f + g
        """
    ).strip()
    (package / "a.py").write_text(block + "\n")
    (package / "b.py").write_text(block + "\n")
    (package / "__init__.py").write_text("")
    ctx = AnalysisContext.load(project / "forgecli")
    findings = DuplicatesAnalyzer().run(ctx)
    assert any(f.rule_id == "DUP001" for f in findings)


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


def test_suggestions_group_by_rule() -> None:
    findings = [
        Finding(
            rule_id="SEC017",
            category="security",
            severity=Severity.HIGH,
            message="x",
            path="a.py",
            line=1,
        ),
        Finding(
            rule_id="SEC017",
            category="security",
            severity=Severity.CRITICAL,
            message="y",
            path="b.py",
            line=2,
        ),
        Finding(
            rule_id="PERF001",
            category="performance",
            severity=Severity.MEDIUM,
            message="z",
            path="c.py",
            line=3,
        ),
    ]
    suggestions = build_suggestions(findings)
    assert len(suggestions) == 2
    # Sorted by severity first.
    assert suggestions[0].severity is Severity.CRITICAL
    assert suggestions[0].title == "Avoid pickle.load()"
    assert suggestions[0].count == 2
    assert suggestions[1].title.startswith("Avoid blocking I/O")


# ---------------------------------------------------------------------------
# RepositoryReview
# ---------------------------------------------------------------------------


def test_review_repository_runs_all_analyzers(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    package = project / "forgecli" / "core"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    long_body_lines = ["    pass" for _ in range(100)]
    src = (
        "import pickle\n"
        "pickle.load(f)\n"
        "\n"
        "def _dead():\n"
        "    return 1\n"
        "\n"
        "async def f():\n"
        "    with open('x') as fh:\n"
        "        return fh.read()\n"
        "\n"
        "def big(x):\n"
        + "\n".join(long_body_lines) + "\n"
    )
    (package / "x.py").write_text(src)
    review = review_repository(project)
    assert any(f.rule_id == "SEC017" for f in review.findings)
    assert any(f.rule_id == "DEAD001" for f in review.findings)
    assert any(f.rule_id == "PERF001" for f in review.findings)
    assert any(f.rule_id == "CPLX001" for f in review.findings)
    assert review.suggestions
    counts = review.counts_by_severity()
    assert sum(counts.values()) == len(review.findings)


def test_default_analyzers_returns_six() -> None:
    analyzers = default_analyzers()
    assert len(analyzers) == 6


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def test_review_to_json_round_trip(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "forgecli" / "x").mkdir(parents=True)
    (project / "forgecli" / "x" / "__init__.py").write_text("")
    (project / "forgecli" / "x" / "a.py").write_text("x = 1\n")
    review = review_repository(project)
    payload = review.to_dict()
    import json

    assert json.loads(review_to_json(review)) == payload


def test_review_to_markdown_contains_sections(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "forgecli" / "x").mkdir(parents=True)
    (project / "forgecli" / "x" / "__init__.py").write_text("")
    (project / "forgecli" / "x" / "a.py").write_text("x = 1\n")
    review = review_repository(project)
    md = review_to_markdown(review)
    assert "# Review:" in md
    assert "## Summary" in md
    assert "Files analyzed" in md


def test_finding_to_dict_shape() -> None:
    finding = Finding(
        rule_id="X",
        category="security",
        severity=Severity.HIGH,
        message="y",
        path="a.py",
        line=1,
    )
    payload = finding.to_dict()
    assert payload["rule_id"] == "X"
    assert payload["severity"] == "high"
    assert payload["path"] == "a.py"


def test_suggestion_dataclass() -> None:
    s = Suggestion(
        title="x",
        severity=Severity.LOW,
        category="security",
    )
    assert s.count == 0


def test_render_findings_capping_and_grouping() -> None:
    from forgecli.review.report import _render_findings

    findings = [
        Finding(rule_id=f"R{i}", category="security", severity=Severity.HIGH, message="msg")
        for i in range(12)
    ]
    # Under 10 by default
    group_default = _render_findings(findings, full=False)
    header_panel = group_default.renderables[0]
    assert "Top 10" in str(header_panel.renderable)
    
    group_full = _render_findings(findings, full=True)
    header_panel_full = group_full.renderables[0]
    assert "Findings" in str(header_panel_full.renderable)
