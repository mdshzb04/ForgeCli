"""Tests for the build pipeline stages."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from forgecli.build import BuildContext
from forgecli.build.apply import (
    apply_unified_diff,
    parse_unified_diff,
)
from forgecli.build.diff_extract import extract_diff
from forgecli.build.pipeline import build_context_from, default_pipeline
from forgecli.build.summarize import build_summary, result_to_dict
from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Role,
)
from forgecli.providers.mock import MockProvider, MockProviderConfig
from forgecli.providers.router import ModelRouter
from forgecli.providers.router_state import RouterState

# ---------------------------------------------------------------------------
# Diff extraction
# ---------------------------------------------------------------------------


def test_extract_diff_finds_git_diff_block() -> None:
    text = (
        "Here you go:\n"
        "```diff\n"
        "diff --git a/foo.py b/foo.py\n"
        "index 0000..1111 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
        "```\n"
        "All done."
    )
    diff = extract_diff(text)
    assert diff.startswith("diff --git a/foo.py")
    assert "--- a/foo.py" in diff
    assert "+new" in diff


def test_extract_diff_returns_empty_when_no_diff() -> None:
    assert extract_diff("just prose, no diff here") == ""


def test_extract_diff_handles_unified_header() -> None:
    text = "preamble\n--- a/x\n+++ b/x\n@@\n-old\n+new\n"
    diff = extract_diff(text)
    assert "--- a/x" in diff


def test_extract_diff_preserves_hunk_body_and_context() -> None:
    """Regression: context lines (starting with a space) used to be trimmed."""
    text = (
        "diff --git a/greet.py b/greet.py\n"
        "index 1111..2222 100644\n"
        "--- a/greet.py\n+++ b/greet.py\n"
        "@@ -1,2 +1,5 @@\n"
        " def greet(name):\n"
        "-    return f\"Hi, {name}!\"\n"
        "+    if not name:\n"
        "+        return \"Hello, stranger!\"\n"
        "+    return f\"Hi, {name}!\"\n"
        "+\n"
        "+def is_anonymous(name):\n"
        "+    return not name\n"
    )
    diff = extract_diff(text)
    assert " def greet(name):" in diff
    assert "+def is_anonymous(name):" in diff
    assert diff.endswith("+    return not name\n")


def test_extract_diff_strips_markdown_code_fence() -> None:
    """Models often wrap their diff in ```diff ... ``` fences."""
    text = (
        "Here you go:\n"
        "```diff\n"
        "diff --git a/x.py b/x.py\n"
        "index 1111..2222 100644\n"
        "--- a/x.py\n+++ b/x.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "```\n"
        "All done."
    )
    diff = extract_diff(text)
    assert diff.startswith("diff --git a/x.py b/x.py")
    assert "+new" in diff
    assert "Here you go" not in diff
    assert "```" not in diff


def test_extract_diff_strips_plain_fence_without_language() -> None:
    text = (
        "```\n"
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n+++ b/x.py\n@@\n-old\n+new\n"
        "```"
    )
    diff = extract_diff(text)
    assert diff.startswith("diff --git")


# ---------------------------------------------------------------------------
# Diff application
# ---------------------------------------------------------------------------


def test_parse_unified_diff_single_file(tmp_path: Path) -> None:
    diff = (
        "diff --git a/hello.py b/hello.py\n"
        "index 1111..2222 100644\n"
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-print('hi')\n"
        "+print('hello')\n"
    )
    parsed = parse_unified_diff(diff)
    assert len(parsed) == 1
    assert parsed[0].path == "hello.py"
    assert "print('hello')" in parsed[0].new_content
    assert "print('hi')" not in parsed[0].new_content


def test_parse_unified_diff_multiple_files() -> None:
    diff = (
        "--- a/a.py\n+++ b/a.py\n@@\n-x\n+X\n"
        "--- a/b.py\n+++ b/b.py\n@@\n-y\n+Y\n"
    )
    parsed = parse_unified_diff(diff)
    assert [p.path for p in parsed] == ["a.py", "b.py"]


def test_apply_unified_diff_with_parser(tmp_path: Path) -> None:
    diff = (
        "--- a/greet.py\n+++ b/greet.py\n@@\n-print('hi')\n+print('hello')\n"
    )
    touched = apply_unified_diff(diff, tmp_path)
    assert len(touched) == 1
    assert touched[0].name == "greet.py"
    assert (tmp_path / "greet.py").read_text(encoding="utf-8").strip() == "print('hello')"


def test_apply_unified_diff_with_git(tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git not on PATH")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "hi.py"
    target.write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "hi.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    diff = (
        "diff --git a/hi.py b/hi.py\n"
        "index 1111..2222 100644\n"
        "--- a/hi.py\n+++ b/hi.py\n@@ -1 +1 @@\n-print('hi')\n+print('hello')\n"
    )
    touched = apply_unified_diff(diff, tmp_path)
    assert target.read_text(encoding="utf-8").strip() == "print('hello')"
    assert touched


# ---------------------------------------------------------------------------
# Ponytail stage
# ---------------------------------------------------------------------------


def test_ponytail_stage_uses_ruleset() -> None:
    from forgecli.build.optimize import ponytail_optimization
    from forgecli.optimizer.ponytail import (
        Intensity,
        PonytailRulesetOptimizer,
    )

    optimizer = PonytailRulesetOptimizer(intensity=Intensity.FULL)
    context = BuildContext(prompt="add a foo", root=Path("/tmp"))
    context.extras["optimizer"] = optimizer
    out = asyncio.run(ponytail_optimization(context))
    assert out.optimized_request is not None
    assert any(m.role is Role.SYSTEM for m in out.optimized_request.messages)


def test_ponytail_stage_works_without_optimizer() -> None:
    from forgecli.build.optimize import ponytail_optimization

    context = BuildContext(prompt="add a foo", root=Path("/tmp"))
    out = asyncio.run(ponytail_optimization(context))
    assert out.optimized_request is not None


# ---------------------------------------------------------------------------
# Graphify retrieval stage
# ---------------------------------------------------------------------------


def test_graphify_retrieval_uses_snapshot(tmp_path: Path) -> None:
    from forgecli.build.retrieval import graphify_retrieval
    from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
    from forgecli.graph.repository import GraphEdge, GraphNode, GraphSnapshot

    graph = GraphifyRepositoryGraph(root=tmp_path)
    snapshot = GraphSnapshot(
        root=str(tmp_path),
        nodes=(
            GraphNode(id="a", label="auth.py", source_file="auth.py"),
            GraphNode(id="b", label="boring.py", source_file="boring.py"),
        ),
        edges=(
            GraphEdge(source="a", target="b", relation="imports"),
        ),
    )
    graph._cached = snapshot  # type: ignore[attr-defined]

    class _GraphProxy:
        async def load(self):
            return snapshot

        def search(self, query, *, limit=20):
            return snapshot.search(query, limit=limit)

    context = BuildContext(prompt="how does auth.py work?", root=tmp_path)
    context.extras["graph"] = _GraphProxy()
    out = asyncio.run(graphify_retrieval(context))
    assert "auth.py" in out.retrieval
    assert "boring.py" not in out.retrieval


def test_graphify_retrieval_handles_missing_graph(tmp_path: Path) -> None:
    from forgecli.build.retrieval import graphify_retrieval

    context = BuildContext(prompt="anything", root=tmp_path)
    out = asyncio.run(graphify_retrieval(context))
    assert out.retrieval == ""


# ---------------------------------------------------------------------------
# LLM stage
# ---------------------------------------------------------------------------


def test_llm_stage_calls_provider(tmp_path: Path) -> None:
    from forgecli.build.llm import llm_call

    class _StubProvider:
        name = "stub"

        def __init__(self) -> None:
            self.last_request: ChatRequest | None = None

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.last_request = request
            return ChatResponse(
                model=request.model or "m",
                message=ChatMessage(role=Role.ASSISTANT, content="diff --git a/x b/x\n"),
            )

    provider = _StubProvider()
    context = BuildContext(prompt="add a function", root=tmp_path)
    context.extras["provider"] = provider
    out = asyncio.run(llm_call(context))
    assert out.response is not None
    assert out.response.message.content.startswith("diff --git")


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------


def test_default_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    provider = MockProvider(MockProviderConfig())
    # Patch the mock provider's chat to return a real diff.
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index 1111..2222 100644\n"
        "--- a/foo.py\n+++ b/foo.py\n@@ -0,0 +1,2 @@\n"
        "+def hi():\n"
        "+    return 'hi'\n"
    )
    original_chat = provider.chat

    async def _chat_with_diff(request: ChatRequest) -> ChatResponse:
        response = await original_chat(request)
        return ChatResponse(
            model=response.model,
            message=ChatMessage(role=Role.ASSISTANT, content=diff),
            finish_reason=response.finish_reason,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
        )

    provider.chat = _chat_with_diff  # type: ignore[method-assign]

    pipeline = default_pipeline(
        provider=provider,
        optimizer=None,
        graph=None,
        test_command="true",  # always-succeeding test command
    )
    context = build_context_from(
        "add a foo() function",
        root=tmp_path,
        router=ModelRouter(),
        state=RouterState(choice="mock"),
    )
    result = asyncio.run(pipeline.run(context))
    assert result.success
    assert result.context.applied_files
    assert (tmp_path / "foo.py").exists()
    assert "def hi" in (tmp_path / "foo.py").read_text(encoding="utf-8")
    assert result.context.summary


def test_llm_stage_retries_on_transient_failure(tmp_path: Path) -> None:
    from forgecli.build.llm import llm_call
    from forgecli.core.errors import ProviderError

    class _FlakyProvider:
        name = "flaky"
        calls = 0

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.calls += 1
            if self.calls < 3:
                raise ProviderError(f"openai chat failed ({503})")
            return ChatResponse(
                model="m",
                message=ChatMessage(role=Role.ASSISTANT, content="diff --git a/x b/x\n"),
            )

    provider = _FlakyProvider()
    context = BuildContext(prompt="x", root=tmp_path)
    context.extras["provider"] = provider
    context.extras["retries"] = 3
    out = asyncio.run(llm_call(context))
    assert out.response is not None
    assert provider.calls == 3


def test_llm_stage_does_not_retry_on_permanent_failure(tmp_path: Path) -> None:
    from forgecli.build.llm import llm_call
    from forgecli.core.errors import ProviderError

    class _BadProvider:
        name = "bad"
        calls = 0

        async def chat(self, request: ChatRequest) -> ChatResponse:
            self.calls += 1
            raise ProviderError("openai chat failed (401): unauthorized")

    provider = _BadProvider()
    context = BuildContext(prompt="x", root=tmp_path)
    context.extras["provider"] = provider
    context.extras["retries"] = 5
    with pytest.raises(ProviderError, match="401"):
        asyncio.run(llm_call(context))
    assert provider.calls == 1


def test_pipeline_short_circuits_on_stage_failure(tmp_path: Path) -> None:
    provider = MockProvider(MockProviderConfig())

    async def _boom(_request):
        raise RuntimeError("kaboom")

    provider.chat = _boom  # type: ignore[method-assign]

    pipeline = default_pipeline(
        provider=provider,
        optimizer=None,
        graph=None,
        test_command="true",
    )
    context = build_context_from(
        "anything", root=tmp_path, router=ModelRouter(), state=RouterState()
    )
    result = asyncio.run(pipeline.run(context))
    assert not result.success
    assert result.failure_stage == "llm"


def test_pipeline_records_stage_durations(tmp_path: Path) -> None:
    provider = MockProvider(MockProviderConfig())
    pipeline = default_pipeline(
        provider=provider,
        optimizer=None,
        graph=None,
        test_command="true",
    )
    context = build_context_from("noop", root=tmp_path, router=ModelRouter())
    result = asyncio.run(pipeline.run(context))
    assert result.context.stages
    for record in result.context.stages:
        assert record.duration_seconds is not None
        assert record.duration_seconds >= 0


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------


def test_summarize_stage_populates_summary(tmp_path: Path) -> None:
    from forgecli.build.summarize import summarize

    context = BuildContext(prompt="add a function", root=tmp_path)
    context.applied_files = [tmp_path / "a.py", tmp_path / "b.py"]
    context.test_returncode = 0
    out = asyncio.run(summarize(context))
    assert "add a function" in out.summary
    assert "Tests: passed" in out.summary
    assert "a.py" in out.summary
    assert "b.py" in out.summary


def test_result_to_dict_shape(tmp_path: Path) -> None:
    from forgecli.build import BuildResult

    context = BuildContext(prompt="x", root=tmp_path)
    context.applied_files = [tmp_path / "f.py"]
    payload = result_to_dict(BuildResult(success=True, context=context))
    assert payload["success"] is True
    assert payload["applied_files"] == [str(tmp_path / "f.py")]
    assert isinstance(payload["stages"], list)


def test_build_summary_records_test_failures(tmp_path: Path) -> None:
    context = BuildContext(prompt="x", root=tmp_path)
    context.test_returncode = 1
    context.test_stderr = "1 test failed"
    summary = build_summary(context)
    assert "FAILED" in summary
    assert "1 test failed" in summary


# Silence unused-import warnings for symbols only used in some branches.
_ = AsyncMock
