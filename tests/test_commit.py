"""Tests for the semantic commit pipeline."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from forgecli.commit.analyzer import (
    CommitAnalyzer,
    CommitKind,
)
from forgecli.commit.changelog import Changelog
from forgecli.commit.git_utils import (
    GitRepoError,
    current_branch,
    is_git_repo,
)
from forgecli.commit.message import build_message, build_subject
from forgecli.commit.release_notes import build_release_notes

# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


def test_analyzer_returns_chore_for_empty_diff() -> None:
    analysis = CommitAnalyzer().analyze("")
    assert analysis.kind is CommitKind.CHORE
    assert "no changes" in analysis.summary.lower()
    assert analysis.files == []


def test_analyzer_detects_feature_kind() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/graph/awesome.py b/forgecli/graph/awesome.py
        new file mode 100644
        index 0000000..abc1234
        --- /dev/null
        +++ b/forgecli/graph/awesome.py
        @@ -0,0 +1,5 @@
        +def hello():
        +    return "hi"
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.kind is CommitKind.FEAT
    assert analysis.scope == "graph"
    assert "graph" in analysis.summary


def test_analyzer_detects_fix_kind_via_test_changes() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/tests/test_x.py b/tests/test_x.py
        --- a/tests/test_x.py
        +++ b/tests/test_x.py
        @@ -1,1 +1,2 @@
         def test_x():
        +    assert x == 1
        """
    ).strip()
    # A tests-only change is correctly classified.
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.kind is CommitKind.TEST


def test_analyzer_counts_insertions_and_deletions() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        --- a/forgecli/x.py
        +++ b/forgecli/x.py
        @@ -1,2 +1,3 @@
         def a():
        -    return 1
        +    return 2
        +    return 3
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.stats["insertions"] == 2
    assert analysis.stats["deletions"] == 1
    assert analysis.files[0].insertions == 2
    assert analysis.files[0].deletions == 1


def test_analyzer_detects_breaking_change_marker() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        --- a/forgecli/x.py
        +++ b/forgecli/x.py
        @@ -0,0 +1,3 @@
        +def bar():
        +    pass
        +
        +BREAKING CHANGE: removed foo()
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.breaking is True


def test_analyzer_does_not_flag_breaking_from_unchanged_code() -> None:
    """`BREAKING CHANGE` only counts as a footer, not as a string literal."""
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        --- a/forgecli/x.py
        +++ b/forgecli/x.py
        @@ -1,3 +1,4 @@
         # This file discusses the BREAKING CHANGE policy
         # but the change itself is additive.
        +x = 1
         y = 2
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.breaking is False


def test_analyzer_detects_conventional_exclamation_marker() -> None:
    """A real `feat!:` or `feat(scope)!:` subject should mark breaking."""
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        --- a/forgecli/x.py
        +++ b/forgecli/x.py
        @@ -0,0 +1,2 @@
        +feat!: drop the legacy API
        +x = 1
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.breaking is True


def test_analyzer_picks_scope_from_top_dir() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/cli/commands_x.py b/forgecli/cli/commands_x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/cli/commands_x.py
        @@ -0,0 +1,1 @@
        +print("x")
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.scope == "cli"


def test_analyzer_scope_is_none_for_mixed_scopes() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/cli/a.py b/forgecli/cli/a.py
        --- a/forgecli/cli/a.py
        +++ b/forgecli/cli/a.py
        @@ -0,0 +1,1 @@
        +x
        diff --git a/forgecli/graph/b.py b/forgecli/graph/b.py
        --- a/forgecli/graph/b.py
        +++ b/forgecli/graph/b.py
        @@ -0,0 +1,1 @@
        +y
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.scope is None


def test_analyzer_classifies_documentation() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/README.md b/README.md
        --- a/README.md
        +++ b/README.md
        @@ -1,1 +1,2 @@
         # Title
        +A new section.
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.kind is CommitKind.DOCS


def test_analyzer_classifies_ci() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
        new file mode 100644
        --- /dev/null
        +++ b/.github/workflows/ci.yml
        @@ -0,0 +1,2 @@
        +name: CI
        +on: [push]
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert analysis.kind is CommitKind.CI


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


def test_message_subject_is_summary() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/cli/commands_x.py b/forgecli/cli/commands_x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/cli/commands_x.py
        @@ -0,0 +1,1 @@
        +print("x")
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    assert build_subject(analysis) == analysis.summary


def test_message_includes_body_and_breaking_footer() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/x.py
        @@ -0,0 +1,3 @@
        +x = 1
        +
        +BREAKING CHANGE: removed foo()
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    msg = build_message(analysis)
    assert analysis.summary in msg
    assert "Files:" in msg
    assert "BREAKING CHANGE" in msg


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------


def test_changelog_round_trip(tmp_path: Path) -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/cli/x.py b/forgecli/cli/x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/cli/x.py
        @@ -0,0 +1,1 @@
        +x = 1
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    cl = Changelog()
    cl.add(analysis)
    path = tmp_path / "CHANGELOG.md"
    cl.save(path)
    text = path.read_text(encoding="utf-8")
    assert "# Changelog" in text
    assert "[Unreleased]" in text
    assert "Features" in text
    assert "cli(x.py)" in text or "x.py" in text

    # Reload and ensure the entry persists.
    reloaded = Changelog.load(path)
    assert len(reloaded.unreleased) == 1


def test_changelog_release_promotes_unreleased() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/x.py
        @@ -0,0 +1,1 @@
        +x = 1
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    cl = Changelog()
    cl.add(analysis)
    released = cl.release("1.0.0", today="2024-05-12")
    assert released.version == "1.0.0"
    assert released.date == "2024-05-12"
    assert cl.unreleased == []
    assert cl.releases[0] is released


def test_changelog_release_empty_raises() -> None:
    cl = Changelog()
    with pytest.raises(ValueError):
        cl.release("0.1.0")


def test_changelog_groups_by_kind() -> None:
    diff_feat = textwrap.dedent(
        """
        diff --git a/forgecli/cli/x.py b/forgecli/cli/x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/cli/x.py
        @@ -0,0 +1,1 @@
        +x
        """
    ).strip()
    diff_fix = textwrap.dedent(
        """
        diff --git a/forgecli/cli/y.py b/forgecli/cli/y.py
        --- a/forgecli/cli/y.py
        +++ b/forgecli/cli/y.py
        @@ -1,1 +1,1 @@
        -broken
        +fixed
        """
    ).strip()
    cl = Changelog()
    cl.add(CommitAnalyzer().analyze(diff_feat))
    cl.add(CommitAnalyzer().analyze(diff_fix))
    text = cl.to_markdown()
    # Features appear before Bug Fixes.
    feat_idx = text.index("### Features")
    fix_idx = text.index("### Bug Fixes")
    assert feat_idx < fix_idx


# ---------------------------------------------------------------------------
# Release notes
# ---------------------------------------------------------------------------


def test_release_notes_includes_breaking_callout() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/x.py
        @@ -0,0 +1,3 @@
        +x = 1
        +
        +BREAKING CHANGE: y
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    notes = build_release_notes("1.0.0", [analysis], previous_version="0.9.0")
    text = notes.render()
    assert "# Release 1.0.0" in text
    assert "## Breaking changes" in text
    assert "1 bug fix" in text or "1 new feature" in text or "Changes" in text
    assert "v0.9.0...v1.0.0" in text


def test_release_notes_handles_empty_list() -> None:
    notes = build_release_notes("1.0.0", [])
    text = notes.render()
    assert "no user-facing changes" in text


def test_release_notes_statistics_section() -> None:
    diff = textwrap.dedent(
        """
        diff --git a/forgecli/x.py b/forgecli/x.py
        new file mode 100644
        --- /dev/null
        +++ b/forgecli/x.py
        @@ -0,0 +1,3 @@
        +x = 1
        +y = 2
        +z = 3
        """
    ).strip()
    analysis = CommitAnalyzer().analyze(diff)
    notes = build_release_notes("1.0.0", [analysis])
    text = notes.render()
    assert "Lines added: 3" in text
    assert "Files touched: 1" in text


# ---------------------------------------------------------------------------
# Git utils
# ---------------------------------------------------------------------------


def test_is_git_repo_true_for_git_repo(tmp_path: Path) -> None:
    import subprocess

    if not _git_available():
        pytest.skip("git not available")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert is_git_repo(tmp_path) is True


def test_is_git_repo_false_for_non_git(tmp_path: Path) -> None:
    assert is_git_repo(tmp_path) is False


def test_current_branch_after_init(tmp_path: Path) -> None:
    import subprocess

    if not _git_available():
        pytest.skip("git not available")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    # Configure identity to make the test hermetic.
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    assert current_branch(tmp_path) == "main"


def test_git_utils_raises_on_missing_binary(tmp_path: Path) -> None:
    from forgecli.commit import git_utils

    original = git_utils.subprocess.run
    try:
        git_utils.subprocess.run = _raise_file_not_found
        with pytest.raises(GitRepoError, match="git executable not found"):
            is_git_repo(tmp_path)
    finally:
        git_utils.subprocess.run = original


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------


def test_cli_commit_non_git(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from forgecli.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["commit", "-p", str(tmp_path)])
    assert result.exit_code == 1
    assert "is not" in result.output and "git working tree" in result.output


def test_cli_commit_no_staged_changes(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from forgecli.cli.main import app

    monkeypatch.setattr("forgecli.cli.commands_commit.is_git_repo", lambda _: True)
    monkeypatch.setattr("forgecli.cli.commands_commit.diff_staged", lambda _: "")

    runner = CliRunner()
    result = runner.invoke(app, ["commit", "-p", str(tmp_path)])
    assert result.exit_code == 1
    assert "No staged changes found." in result.output


def test_cli_commit_success(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from forgecli.cli.main import app
    from forgecli.providers.mock import MockProvider, MockProviderConfig
    from forgecli.providers.router import RouteDecision, SelectionMode

    monkeypatch.setattr("forgecli.cli.commands_commit.is_git_repo", lambda _: True)
    monkeypatch.setattr("forgecli.cli.commands_commit.diff_staged", lambda _: "diff data")

    # Mock input to return immediately (simulating pressing Enter)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")

    # Mock _run_git to avoid actually calling git commit
    git_calls = []
    monkeypatch.setattr("forgecli.cli.commands_commit._run_git", lambda args, proj: git_calls.append(args))

    # Mock provider and decision resolver
    mock_provider = MockProvider(MockProviderConfig())
    mock_decision = RouteDecision(provider_name="mock", model="mock-model", mode=SelectionMode.EXPLICIT)
    monkeypatch.setattr(
        "forgecli.cli.bootstrap.resolve_provider_and_decision",
        lambda live, cwd: (mock_provider, mock_decision)
    )

    runner = CliRunner()
    result = runner.invoke(app, ["commit", "-p", str(tmp_path)])

    assert result.exit_code == 0
    assert "AI Commit Preview" in result.output
    assert "✓ Commit Created" in result.output
    assert len(git_calls) == 2
    assert git_calls[0][0] == "commit"
    assert "-m" in git_calls[0]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    import shutil

    return shutil.which("git") is not None


def _raise_file_not_found(*args, **kwargs):
    raise FileNotFoundError("simulated")
