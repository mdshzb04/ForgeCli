"""Tests for the plugin system, intent classifier, and orchestrator."""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from forgecli.orchestrator import (
    AskWorkflow,
    BuildWorkflow,
    CommitWorkflow,
    DocsWorkflow,
    ExplainWorkflow,
    HeuristicIntentClassifier,
    Intent,
    Orchestrator,
    PlanWorkflow,
    ReviewWorkflow,
    build_orchestrator,
)
from forgecli.plugins import (
    IntentClassifier,
    IntentPrediction,
    PluginContext,
    PluginRegistry,
    Workflow,
    discover_plugins,
)
from forgecli.providers.mock import MockProvider, MockProviderConfig

# ---------------------------------------------------------------------------
# HeuristicIntentClassifier
# ---------------------------------------------------------------------------


def test_heuristic_classifier_recognizes_build() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("Add a foo() function to the CLI")
    assert prediction.intent is Intent.BUILD


def test_heuristic_classifier_recognizes_ask() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("What does this module do?")
    assert prediction.intent is Intent.ASK


def test_heuristic_classifier_recognizes_plan() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("Design the architecture for a new service")
    assert prediction.intent is Intent.PLAN


def test_heuristic_classifier_recognizes_docs() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("Document the API in a README")
    assert prediction.intent is Intent.DOCS


def test_heuristic_classifier_recognizes_review() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("Audit the code for security issues")
    assert prediction.intent is Intent.REVIEW


def test_heuristic_classifier_recognizes_explain() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("Explain this function for me")
    assert prediction.intent is Intent.EXPLAIN


def test_heuristic_classifier_recognizes_commit() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("Make a commit with these changes")
    assert prediction.intent is Intent.COMMIT


def test_heuristic_classifier_handles_empty() -> None:
    classifier = HeuristicIntentClassifier()
    prediction = classifier.classify("")
    assert prediction.intent is Intent.UNKNOWN


# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------


def test_registry_starts_empty() -> None:
    registry = PluginRegistry()
    assert registry.workflows == []
    assert registry.providers == {}
    assert registry.analyzers == []


def test_registry_can_register_workflows() -> None:
    registry = PluginRegistry()
    workflow = AskWorkflow()
    registry.register_workflow(workflow)
    assert registry.workflows == [workflow]


def test_discover_plugins_handles_missing_entry_points() -> None:
    registry = PluginRegistry()
    # Should not raise even if no plugins are installed.
    assert discover_plugins(registry, group="nonexistent.group") == []


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _make_orchestrator() -> Orchestrator:
    provider = MockProvider(MockProviderConfig())
    registry = PluginRegistry()
    registry.register_classifier(HeuristicIntentClassifier())
    registry.register_workflow(BuildWorkflow(provider=provider))
    registry.register_workflow(PlanWorkflow())
    registry.register_workflow(AskWorkflow())
    registry.register_workflow(ReviewWorkflow())
    registry.register_workflow(ExplainWorkflow())
    registry.register_workflow(CommitWorkflow())
    return Orchestrator(registry, provider=provider)


def test_orchestrator_picks_ask_workflow() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("What does this function do?"))
    assert result.intent is Intent.ASK
    assert result.workflow == "ask"
    assert result.success


def test_orchestrator_picks_build_workflow() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("Add a foo() function"))
    assert result.intent is Intent.BUILD
    assert result.workflow == "build"
    assert result.success


def test_orchestrator_picks_plan_workflow() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("Design the architecture for a CRM"))
    assert result.intent is Intent.PLAN
    assert result.workflow == "plan"


def test_orchestrator_picks_explain_workflow() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("Explain this function for me"))
    assert result.intent is Intent.EXPLAIN
    assert result.workflow == "explain"


def test_orchestrator_picks_commit_workflow() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("Make a commit"))
    assert result.intent is Intent.COMMIT
    assert result.workflow == "commit"


def test_orchestrator_falls_back_to_build() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("hello world"))
    assert result.intent is Intent.BUILD
    assert result.workflow == "build"


def test_build_orchestrator_wires_defaults() -> None:
    provider = MockProvider(MockProviderConfig())
    registry = PluginRegistry()
    orch = build_orchestrator(registry, provider=provider)
    # All seven default workflows are registered.
    assert {w.name for w in orch.registry.workflows} >= {
        "build", "plan", "ask", "docs", "review", "explain", "commit"
    }


def test_custom_workflow_is_used_when_intent_matches() -> None:
    provider = MockProvider(MockProviderConfig())
    registry = PluginRegistry()
    registry.register_classifier(HeuristicIntentClassifier())

    class CustomAsk(Workflow):
        name = "custom-ask"
        intents = (Intent.ASK,)

        async def run(self, context: PluginContext) -> dict:
            return {"summary": "custom-ask ran", "files_touched": [], "diff": ""}

    registry.register_workflow(CustomAsk())
    # Register a low-priority fallback so we know the custom one wins.
    registry.register_workflow(AskWorkflow())
    orch = Orchestrator(registry, provider=provider)
    # "Tell me how foo() works" classifies as ASK (question word + "tell me")
    result = asyncio.run(orch.run("Tell me how foo() works"))
    assert result.workflow == "custom-ask"


# ---------------------------------------------------------------------------
# Plan workflow
# ---------------------------------------------------------------------------


def test_plan_workflow_returns_software_plan() -> None:
    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run("Design the architecture for a CRM"))
    assert result.workflow == "plan"
    assert "Plan for" in result.summary


# ---------------------------------------------------------------------------
# Build workflow (offline)
# ---------------------------------------------------------------------------


def test_build_workflow_uses_mock_provider() -> None:
    provider = MockProvider(MockProviderConfig())
    registry = PluginRegistry()
    registry.register_classifier(HeuristicIntentClassifier())
    orch = Orchestrator(registry, provider=provider)
    # The mock provider echoes the prompt, so no diff is produced; the
    # build still completes successfully and the summary is populated.
    result = asyncio.run(orch.run("Add a foo() function"))
    assert result.workflow == "build"
    assert result.success
    assert result.stages
    assert not result.files_touched  # mock echo, no diff applied


# ---------------------------------------------------------------------------
# Docs workflow
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_docs_workflow_writes_overview(tmp_path: Path) -> None:
    provider = MockProvider(MockProviderConfig())
    registry = PluginRegistry()
    registry.register_classifier(HeuristicIntentClassifier())
    orch = Orchestrator(registry, provider=provider)

    project = tmp_path / "p"
    package = project / "forgecli" / "x"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "mod.py").write_text("def hello():\n    return 'hi'\n")

    result = asyncio.run(_run_orchestrator_in(orch, "Document the API in a README", project))
    assert result.workflow == "docs"
    overview = project / "docs" / "OVERVIEW.md"
    assert overview.exists()
    text = overview.read_text(encoding="utf-8")
    assert "hello" in text


async def _run_orchestrator_in(orch, prompt: str, project: Path):
    """Run the orchestrator with the cwd set to ``project``."""
    import contextlib

    with contextlib.chdir(project):
        return await orch.run(prompt)


# ---------------------------------------------------------------------------
# Custom IntentClassifier
# ---------------------------------------------------------------------------


def test_orchestrator_uses_custom_classifier_first() -> None:
    class _AlwaysAsk(IntentClassifier):
        name = "always-ask"
        priority = 1  # checked first

        def classify(self, prompt, *, history=()):
            return IntentPrediction(Intent.ASK, 0.99, ("forced",))

    provider = MockProvider(MockProviderConfig())
    registry = PluginRegistry()
    registry.register_classifier(_AlwaysAsk())
    registry.register_classifier(HeuristicIntentClassifier())
    registry.register_workflow(AskWorkflow())
    orch = Orchestrator(registry, provider=provider)
    result = asyncio.run(orch.run("Add a foo() function"))
    assert result.intent is Intent.ASK


# Silence unused-import warnings for symbols only used in some branches.
_ = DocsWorkflow
_ = textwrap
