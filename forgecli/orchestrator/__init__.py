"""The top-level ``forge`` orchestrator.

The orchestrator is the single entry point for the
``forge "<prompt>"`` command. It:

1. Classifies the user's intent (:class:`Intent`).
2. Picks a :class:`Workflow` (default ``BuildWorkflow``).
3. Runs the workflow's standard pipeline stages:
   retrieval -> optimization -> LLM call -> diff extract -> apply
   -> test -> auto-fix -> commit -> summary.
4. Returns a :class:`ForgeResult` payload for the CLI to render.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from forgecli.build.apply import apply_diff
from forgecli.build.diff_extract import diff_extraction
from forgecli.build.llm import llm_call
from forgecli.build.optimize import ponytail_optimization
from forgecli.build.retrieval import graphify_retrieval
from forgecli.build.summarize import summarize
from forgecli.core.context import AppContext
from forgecli.plugins import (
    Intent,
    IntentClassifier,
    IntentPrediction,
    PluginContext,
    PluginRegistry,
    Workflow,
)
from forgecli.providers.base import Provider
from forgecli.providers.mock import MockProvider, MockProviderConfig
from forgecli.providers.router import ModelRouter
from forgecli.providers.router_state import load_state

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


class HeuristicIntentClassifier(IntentClassifier):
    """A small, deterministic intent classifier.

    The classifier is intentionally rule-based so the user can inspect
    and override it. Plugins can register richer classifiers (e.g. an
    LLM-based one) via :meth:`PluginRegistry.register_classifier`.
    """

    name = "heuristic"
    priority = 100  # higher priority = checked first

    _QUESTION_WORDS = (
        "what",
        "why",
        "how",
        "when",
        "where",
        "who",
        "which",
        "explain",
        "tell me",
        "describe",
    )
    _DOCS_HINTS = ("document", "docs", "readme", "explain how", "describe the api")
    _PLAN_HINTS = ("plan", "design", "architect", "roadmap", "milestones")
    _REVIEW_HINTS = ("review", "audit", "check the code", "lint")
    _EXPLAIN_HINTS = ("explain this", "what does this do", "how does this work")
    _COMMIT_HINTS = ("commit", "ship this", "make a commit")
    _BUILD_HINTS = (
        "add",
        "implement",
        "build",
        "create",
        "fix",
        "refactor",
        "rewrite",
        "migrate",
        "add jwt",
        "add a",
        "introduce",
        "convert",
        "wire up",
        "set up",
        "bootstrap",
    )

    def classify(
        self, prompt: str, *, history: tuple[str, ...] = ()
    ) -> IntentPrediction:
        text = (prompt or "").strip().lower()
        if not text:
            return IntentPrediction(Intent.UNKNOWN, 0.0, ("empty prompt",))

        if any(hint in text for hint in self._DOCS_HINTS):
            return IntentPrediction(Intent.DOCS, 0.9, ("matched docs hint",))
        if any(hint in text for hint in self._REVIEW_HINTS):
            return IntentPrediction(Intent.REVIEW, 0.9, ("matched review hint",))
        if any(text.startswith(hint) for hint in self._EXPLAIN_HINTS):
            return IntentPrediction(Intent.EXPLAIN, 0.85, ("matched explain hint",))
        if any(hint in text for hint in self._COMMIT_HINTS):
            return IntentPrediction(Intent.COMMIT, 0.8, ("matched commit hint",))
        if any(hint in text for hint in self._PLAN_HINTS) and not any(
            hint in text for hint in self._BUILD_HINTS
        ):
            return IntentPrediction(Intent.PLAN, 0.8, ("matched plan hint",))
        if any(text.startswith(word) for word in self._QUESTION_WORDS):
            return IntentPrediction(Intent.ASK, 0.85, ("starts with question word",))
        if any(hint in text for hint in self._BUILD_HINTS):
            return IntentPrediction(Intent.BUILD, 0.8, ("matched build hint",))
        return IntentPrediction(Intent.BUILD, 0.5, ("default to build",))


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


@dataclass
class ForgeResult:
    """The result of a top-level ``forge "<prompt>"`` invocation."""

    success: bool
    intent: Intent
    workflow: str
    duration_seconds: float
    summary: str
    files_touched: list[Path] = field(default_factory=list)
    diff: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
    stages: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class BuildWorkflow(Workflow):
    """The default workflow: full Graphify -> Ponytail -> LLM -> apply -> test."""

    name = "build"
    intents = (Intent.BUILD, Intent.UNKNOWN)

    def __init__(
        self,
        *,
        provider: Provider,
        graphify=None,
        optimizer=None,
        test_command: str | None = None,
        auto_fix: bool = True,
        max_fix_attempts: int = 2,
    ) -> None:
        self._provider = provider
        self._graphify = graphify
        self._optimizer = optimizer
        self._test_command = test_command
        self._auto_fix = auto_fix
        self._max_fix_attempts = max_fix_attempts

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.build import BuildContext, BuildPipeline

        app_context = context.app_context
        target = Path.cwd()
        decision = self._resolve_decision(app_context)

        build_context = BuildContext(prompt=context.prompt, root=target, decision=decision)
        build_context.extras.update(context.extras.get("build_extras", {}))
        build_context.extras["provider"] = self._provider
        if self._graphify is not None:
            build_context.extras["graph"] = self._graphify
        if self._optimizer is not None:
            build_context.extras["optimizer"] = self._optimizer
        if self._test_command is not None:
            build_context.extras["test_command"] = self._test_command

        stages: list[tuple[str, Any]] = [
            ("graphify-retrieval", graphify_retrieval),
            ("ponytail-optimize", ponytail_optimization),
            ("llm", llm_call),
            ("diff-extract", diff_extraction),
            ("apply-diff", apply_diff),
            ("run-tests", _run_tests),
            ("summarize", summarize),
        ]
        pipeline = BuildPipeline(stages)
        result = await pipeline.run(build_context)

        if (
            self._auto_fix
            and result.context.test_returncode not in (0, None)
            and result.context.applied_files
        ):
            fixed = await self._auto_fix_loop(target, build_context, result)
            if fixed:
                result = fixed

        await summarize(build_context)
        return {
            "summary": build_context.summary,
            "files_touched": build_context.applied_files,
            "diff": build_context.diff_text,
            "decision": decision,
            "stages": [
                {
                    "name": stage.name,
                    "status": stage.status.value,
                    "duration_seconds": stage.duration_seconds,
                    "error": stage.error,
                }
                for stage in build_context.stages
            ],
            "result": result,
        }

    def _resolve_decision(self, app_context: AppContext):
        from forgecli.providers.router import SelectionMode

        state = load_state(app_context.paths.data_dir / "router.json")
        router = ModelRouter()
        decision = router.select(state.choice)
        if isinstance(self._provider, MockProvider):
            return type(decision)(
                provider_name=self._provider.name,
                model=decision.model,
                mode=SelectionMode.FALLBACK,
                cost_in=0.0,
                cost_out=0.0,
            )
        return decision

    async def _auto_fix_loop(
        self, target: Path, build_context, last_result
    ):
        """Re-run the LLM stage when tests fail, up to ``max_fix_attempts``."""
        from forgecli.build import BuildPipeline

        for _ in range(self._max_fix_attempts):
            # Build a focused "fix the tests" prompt and re-run the
            # LLM/diff/apply/test stages in a tiny pipeline.
            from forgecli.build.diff_extract import diff_extraction
            from forgecli.build.llm import llm_call
            from forgecli.build.optimize import ponytail_optimization
            from forgecli.build.summarize import summarize

            fix_prompt = (
                f"Tests failed:\n\n{build_context.test_stderr[-2000:]}\n\n"
                f"Original task: {build_context.prompt}\n\n"
                "Return a unified diff that fixes the failing tests. "
                "Do not change unrelated code."
            )
            fix_context = type(build_context)(
                prompt=fix_prompt, root=build_context.root, decision=build_context.decision
            )
            fix_context.extras.update(build_context.extras)
            fix_context.extras["retries"] = 0
            fix_pipeline = BuildPipeline(
                [
                    ("ponytail-optimize", ponytail_optimization),
                    ("llm", llm_call),
                    ("diff-extract", diff_extraction),
                    ("apply-diff", apply_diff),
                    ("run-tests", _run_tests),
                    ("summarize", summarize),
                ]
            )
            new_result = await fix_pipeline.run(fix_context)
            if new_result.context.test_returncode == 0:
                return new_result
        return None


# ---------------------------------------------------------------------------
# Auto-fix test runner (re-uses the build test stage but is callable)
# ---------------------------------------------------------------------------


async def _run_tests(context):
    from forgecli.build.test_run import run_tests as _impl

    return await _impl(context)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Top-level orchestrator for ``forge "<prompt>"``."""

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        provider: Provider,
        decision: Any | None = None,
        workflow_factory: Callable[[Intent], Workflow] | None = None,
        classifier: IntentClassifier | None = None,
    ) -> None:
        self._registry = registry
        self._provider = provider
        self._decision = decision
        self._workflow_factory = workflow_factory or _default_workflow_factory
        self._classifier = classifier or HeuristicIntentClassifier()
        if self._classifier not in self._registry.classifiers:
            self._registry.register_classifier(self._classifier)

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    async def run(self, prompt: str, *, intent: Intent | None = None) -> ForgeResult:
        started = time.perf_counter()
        try:
            if intent is not None:
                prediction = IntentPrediction(intent, 1.0, ("forced intent",))
            else:
                prediction = self._classify(prompt)
            workflow = self._workflow_for(prediction)

            app_ctx = _bootstrap_app_context()
            from forgecli.graph.repository import RepositoryGraph
            from forgecli.optimizer.ponytail import PromptOptimizer

            opt = None
            if app_ctx.container.has(PromptOptimizer):
                opt = app_ctx.container.resolve(PromptOptimizer)  # type: ignore[type-abstract]

            graph = None
            if app_ctx.container.has(RepositoryGraph):
                graph = app_ctx.container.resolve(RepositoryGraph)  # type: ignore[type-abstract]

            build_extras = {
                "provider": self._provider,
                "optimizer": opt,
                "graph": graph,
                "intent": prediction.intent,
                "decision": self._decision,
            }

            plugin_context = PluginContext(
                app_context=app_ctx,
                prompt=prompt,
                intent=prediction.intent,
                extras={
                    "prediction": prediction,
                    "build_extras": build_extras,
                },
            )
            payload = await workflow.run(plugin_context)
        except Exception:
            return ForgeResult(
                success=False,
                intent=Intent.UNKNOWN,
                workflow="(error)",
                duration_seconds=time.perf_counter() - started,
                summary="",
                error=traceback.format_exc(),
            )
        duration = time.perf_counter() - started
        return ForgeResult(
            success=True,
            intent=prediction.intent,
            workflow=workflow.name,
            duration_seconds=duration,
            summary=str(payload.get("summary", "")),
            files_touched=list(payload.get("files_touched") or []),
            diff=str(payload.get("diff") or ""),
            stages=list(payload.get("stages") or []),
            extras=payload,
        )

    def _classify(self, prompt: str) -> IntentPrediction:
        for classifier in self._registry.classifiers_sorted():
            try:
                prediction = classifier.classify(prompt)
            except Exception:
                continue
            if prediction.intent is not Intent.UNKNOWN:
                return prediction
        return IntentPrediction(Intent.BUILD, 0.5, ("fallback to build",))

    def _workflow_for(self, prediction: IntentPrediction) -> Workflow:
        for workflow in self._registry.workflows:
            if workflow.can_handle(prediction.intent, (prediction.rationale and " ") or ""):
                return workflow
        return self._workflow_factory(prediction.intent)


def _default_workflow_factory(intent: Intent) -> Workflow:
    """Pick a default workflow for the given intent."""
    if intent is Intent.ASK:
        return AskWorkflow()
    if intent is Intent.PLAN:
        return PlanWorkflow()
    if intent is Intent.DOCS:
        return DocsWorkflow()
    if intent is Intent.REVIEW:
        return ReviewWorkflow()
    if intent is Intent.EXPLAIN:
        return ExplainWorkflow()
    if intent is Intent.COMMIT:
        return CommitWorkflow()
    # BUILD and UNKNOWN fall through to the heavy pipeline.
    from forgecli.providers.mock import MockProvider

    return BuildWorkflow(provider=MockProvider(MockProviderConfig()))


# ---------------------------------------------------------------------------
# Minimal built-in workflows
# ---------------------------------------------------------------------------


def _asks_for_repo_context(prompt: str) -> bool:
    import re
    text = (prompt or "").strip().lower()
    greetings = {"hi", "hello", "hey", "howdy", "greetings", "good morning", "good afternoon", "good evening", "how are you", "what's up", "yo"}
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return False
    if len(words) <= 3 and any(w in greetings for w in words):
        return False

    keywords = {
        "project", "repository", "repo", "code", "file", "files", "architecture", "implementation", "bug", "bugs",
        "docs", "documentation", "structure", "folder", "directory", "dir", "function", "method", "class", "module",
        "current", "this", "here"
    }
    extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".html", ".css", ".yml", ".yaml", ".toml", "package.json"}
    if any(ext in text for ext in extensions):
        return True

    if any(w in keywords for w in words):
        return True

    return "what is this" in text or "explain this" in text or "this project" in text


class AskWorkflow(Workflow):
    """A conversational Q&A workflow against the project graph."""

    name = "ask"
    intents = (Intent.ASK,)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.build import BuildContext, BuildPipeline
        from forgecli.build.llm import llm_call
        from forgecli.build.optimize import ponytail_optimization
        from forgecli.build.retrieval import graphify_retrieval
        from forgecli.build.summarize import summarize

        # Reuse the early stages of the build pipeline: graph -> opt -> llm.
        decision = context.extras.get("build_extras", {}).get("decision")
        build_context = BuildContext(prompt=context.prompt, root=Path.cwd(), decision=decision)
        build_context.extras.update(context.extras.get("build_extras", {}))

        stages: list[tuple[str, Any]] = []
        if _asks_for_repo_context(context.prompt):
            stages.append(("graphify-retrieval", graphify_retrieval))
        stages.extend([
            ("ponytail-optimize", ponytail_optimization),
            ("llm", llm_call),
            ("summarize", summarize),
        ])

        pipeline = BuildPipeline(stages)
        result = await pipeline.run(build_context)
        if not result.success:
            err = "Pipeline stage failed"
            for r in result.context.stages:
                if r.error:
                    err = r.error
                    break
            raise Exception(f"Stage '{result.failure_stage}' failed: {err}")
        answer = result.context.response.message.content if result.context.response else ""
        return {"summary": answer, "files_touched": [], "diff": ""}


class PlanWorkflow(Workflow):
    name = "plan"
    intents = (Intent.PLAN,)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.planner.render import render_plan
        from forgecli.planner.software import PlannerOptions, build_software_plan

        plan = build_software_plan(context.prompt, PlannerOptions())
        renderables = render_plan(plan)
        return {
            "summary": plan.summary,
            "plan": plan,
            "renderables": renderables,
            "files_touched": [],
            "diff": "",
        }


class DocsWorkflow(Workflow):
    name = "docs"
    intents = (Intent.DOCS,)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.build import BuildContext, BuildPipeline
        from forgecli.build.llm import llm_call
        from forgecli.build.optimize import ponytail_optimization
        from forgecli.build.summarize import summarize

        root = context.app_context.cwd
        files_info = []
        for path in sorted(root.rglob("*.py")):
            if any(part.startswith(".") for part in path.parts):
                continue
            if any(part in {"__pycache__", "node_modules", ".venv", "venv"} for part in path.parts):
                continue
            files_info.append(str(path.relative_to(root)))

        prompt = (
            f"Generate a comprehensive overview documentation for the project '{root.name}'.\n"
            f"Here are the main files in the project:\n"
            + "\n".join(f"- {f}" for f in files_info[:30]) + "\n\n"
            "Produce a clean, professional, and well-structured Markdown document containing:\n"
            "1. Executive Summary of the project purpose.\n"
            "2. High-level architecture overview.\n"
            "3. Key modules and entry points."
        )

        decision = context.extras.get("build_extras", {}).get("decision")
        build_context = BuildContext(prompt=prompt, root=Path.cwd(), decision=decision)
        build_context.extras.update(context.extras.get("build_extras", {}))

        pipeline = BuildPipeline(
            [
                ("ponytail-optimize", ponytail_optimization),
                ("llm", llm_call),
                ("summarize", summarize),
            ]
        )
        result = await pipeline.run(build_context)
        if not result.success:
            err = "Pipeline stage failed"
            for r in result.context.stages:
                if r.error:
                    err = r.error
                    break
            raise Exception(f"Stage '{result.failure_stage}' failed: {err}")
        ai_docs = result.context.response.message.content if result.context.response else ""

        output_dir = root / "docs"
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "OVERVIEW.md"
        target.write_text(ai_docs, encoding="utf-8")

        return {
            "summary": f"Documentation written to {target}",
            "files_touched": [target],
            "diff": "",
        }


class ReviewWorkflow(Workflow):
    name = "review"
    intents = (Intent.REVIEW,)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.build import BuildContext, BuildPipeline
        from forgecli.build.llm import llm_call
        from forgecli.build.optimize import ponytail_optimization
        from forgecli.build.summarize import summarize
        from forgecli.review import review_repository

        review = review_repository(Path.cwd())

        prompt = (
            f"Review the code quality scan findings for the project:\n\n"
            f"Findings: {len(review.findings)} total.\n"
            f"Suggestions: {len(review.suggestions)} total.\n\n"
            f"Summarize the findings and provide key quality improvement recommendations."
        )

        decision = context.extras.get("build_extras", {}).get("decision")
        build_context = BuildContext(prompt=prompt, root=Path.cwd(), decision=decision)
        build_context.extras.update(context.extras.get("build_extras", {}))

        pipeline = BuildPipeline(
            [
                ("ponytail-optimize", ponytail_optimization),
                ("llm", llm_call),
                ("summarize", summarize),
            ]
        )
        result = await pipeline.run(build_context)
        if not result.success:
            err = "Pipeline stage failed"
            for r in result.context.stages:
                if r.error:
                    err = r.error
                    break
            raise Exception(f"Stage '{result.failure_stage}' failed: {err}")
        ai_summary = result.context.response.message.content if result.context.response else ""

        summary = (
            f"Reviewed {review.stats.get('files', 0)} files; "
            f"{len(review.findings)} findings.\n\n"
            f"[bold]AI Summary & Recommendations:[/bold]\n{ai_summary}"
        )
        return {
            "summary": summary,
            "review": review,
            "files_touched": [],
            "diff": "",
        }


class ExplainWorkflow(Workflow):
    name = "explain"
    intents = (Intent.EXPLAIN,)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.build import BuildContext, BuildPipeline
        from forgecli.build.llm import llm_call
        from forgecli.build.optimize import ponytail_optimization
        from forgecli.build.retrieval import graphify_retrieval
        from forgecli.build.summarize import summarize

        prompt = f"Explain the node, file, or symbol: {context.prompt}"
        decision = context.extras.get("build_extras", {}).get("decision")
        build_context = BuildContext(prompt=prompt, root=Path.cwd(), decision=decision)
        build_context.extras.update(context.extras.get("build_extras", {}))

        pipeline = BuildPipeline(
            [
                ("graphify-retrieval", graphify_retrieval),
                ("ponytail-optimize", ponytail_optimization),
                ("llm", llm_call),
                ("summarize", summarize),
            ]
        )
        result = await pipeline.run(build_context)
        if not result.success:
            err = "Pipeline stage failed"
            for r in result.context.stages:
                if r.error:
                    err = r.error
                    break
            raise Exception(f"Stage '{result.failure_stage}' failed: {err}")
        explanation = result.context.response.message.content if result.context.response else ""
        return {"summary": explanation, "files_touched": [], "diff": ""}


class CommitWorkflow(Workflow):
    name = "commit"
    intents = (Intent.COMMIT,)

    async def run(self, context: PluginContext) -> dict[str, Any]:
        from forgecli.commit.analyzer import CommitAnalyzer
        from forgecli.commit.git_utils import diff_staged

        diff = diff_staged(Path.cwd())
        if not diff:
            return {
                "summary": "No staged changes to commit.",
                "files_touched": [],
                "diff": "",
            }
        analysis = CommitAnalyzer().analyze(diff)
        return {
            "summary": analysis.summary,
            "analysis": analysis,
            "files_touched": [],
            "diff": diff,
        }


# ---------------------------------------------------------------------------
# Bootstrap helper
# ---------------------------------------------------------------------------


def _bootstrap_app_context() -> AppContext:
    """Best-effort bootstrap of an :class:`AppContext` for the orchestrator.

    The orchestrator is runnable from a bare ``forge "<prompt>"`` call
    without prior setup. If the bootstrap fails (e.g. no config file)
    we fall back to a minimal in-memory context.
    """
    from forgecli.cli.bootstrap import bootstrap_context
    from forgecli.utils.paths import ProjectPaths

    try:
        return bootstrap_context()
    except Exception:
        from forgecli.config.loader import ConfigLoader
        paths = ProjectPaths.from_env().ensure()
        return AppContext(paths=paths, loader=ConfigLoader())


__all__ = [
    "AskWorkflow",
    "BuildWorkflow",
    "CommitWorkflow",
    "DocsWorkflow",
    "ExplainWorkflow",
    "ForgeResult",
    "HeuristicIntentClassifier",
    "Orchestrator",
    "PlanWorkflow",
    "ReviewWorkflow",
    "build_orchestrator",
]


def build_orchestrator(
    registry: PluginRegistry,
    *,
    provider: Provider,
    decision: Any | None = None,
) -> Orchestrator:
    """Build a default :class:`Orchestrator` for the given registry + provider.

    The function also wires the standard ForgeCLI workflows into the
    registry if they are not already present. This is the composition
    root for the top-level ``forge`` command.
    """
    defaults: list[Workflow] = [
        BuildWorkflow(provider=provider),
        PlanWorkflow(),
        AskWorkflow(),
        DocsWorkflow(),
        ReviewWorkflow(),
        ExplainWorkflow(),
        CommitWorkflow(),
    ]
    existing = {w.name for w in registry.workflows}
    for workflow in defaults:
        if workflow.name not in existing:
            registry.register_workflow(workflow)
    return Orchestrator(registry, provider=provider, decision=decision)
