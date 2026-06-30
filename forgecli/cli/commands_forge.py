"""The top-level ``forge`` command: a free-form prompt that runs the
full pipeline.

Usage:

    forge "Build a FastAPI service for user authentication"
    forge "Create an AI CRM with LangGraph agents"
    forge "Add JWT authentication and Stripe subscriptions"

The command classifies the user's intent (build / ask / plan /
docs / review / explain / commit), picks the right workflow, and
runs the standard pipeline (Graphify retrieval -> Ponytail
optimization -> LLM call -> diff extraction -> apply -> tests ->
auto-fix -> summary).

Plugins may register additional workflows and intent classifiers
via the ``forgecli.plugins`` entry-point group.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, info, success, table, warn
from forgecli.commit.git_utils import GitRepoError, diff_staged
from forgecli.orchestrator import (
    HeuristicIntentClassifier,
    Orchestrator,
    PluginRegistry,
    build_orchestrator,
)

# A single shared registry so subcommands and the top-level command
# share the same plugin state.
_REGISTRY = PluginRegistry()
_REGISTRY.register_classifier(HeuristicIntentClassifier())


def _register_default_workflows(provider, *, test_command: str | None = None) -> None:
    """Register the seven default workflow *instances* under their
    canonical names. Idempotent: re-registering with a different
    provider replaces the previous binding.
    """
    from forgecli.orchestrator import (
        AskWorkflow,
        BuildWorkflow,
        CommitWorkflow,
        DocsWorkflow,
        ExplainWorkflow,
        PlanWorkflow,
        ReviewWorkflow,
    )

    defaults = [
        BuildWorkflow(provider=provider, test_command=test_command),
        PlanWorkflow(),
        AskWorkflow(),
        DocsWorkflow(),
        ReviewWorkflow(),
        ExplainWorkflow(),
        CommitWorkflow(),
    ]
    existing = {w.name for w in _REGISTRY.workflows}
    for workflow in defaults:
        if workflow.name in existing:
            _REGISTRY.workflows[:] = [
                w for w in _REGISTRY.workflows if w.name != workflow.name
            ]
        _REGISTRY.register_workflow(workflow)


def get_registry() -> PluginRegistry:
    return _REGISTRY


app = typer.Typer(
    name="forge",
    help="ForgeCLI: an AI-first developer operating system.",
    no_args_is_help=True,
    add_completion=False,
    invoke_without_command=True,
    rich_markup_mode="rich",
)


def _build_provider_for(*, live: bool, cwd: Path):
    """Build a :class:`Provider` for the current invocation."""
    from forgecli.providers.mock import MockProvider, MockProviderConfig

    if not live:
        return MockProvider(MockProviderConfig())

    from forgecli.providers.base import ProviderRegistry
    from forgecli.providers.router_state import load_state

    app_context = bootstrap_context(cwd=str(cwd))
    state = load_state(app_context.paths.data_dir / "router.json")
    chosen = state.choice or state.provider
    if not chosen:
        from forgecli.config.loader import ConfigLoader
        try:
            settings = ConfigLoader().load()
            chosen = settings.providers.default
        except Exception:
            pass
    if not chosen:
        raise ValueError(
            "No active provider configured. Please authenticate first (e.g. 'forge auth login'), "
            "then set your active provider using 'forge provider use <provider>' and active model using 'forge model use <model>'."
        )

    registry = app_context.container.resolve(ProviderRegistry)
    if not registry.has(chosen):
        raise ValueError(f"Unknown provider '{chosen}'.")
    provider_cls = registry.get(chosen)
    return provider_cls()  # type: ignore[call-arg]


def _build_orchestrator_for(
    *,
    live: bool,
    cwd: Path,
) -> Orchestrator:
    """Backwards-compatible shim that returns an :class:`Orchestrator`."""
    provider = _build_provider_for(live=live, cwd=cwd)
    _register_default_workflows(provider)
    return build_orchestrator(_REGISTRY, provider=provider)


@app.callback(invoke_without_command=True)
def forge_cmd(
    ctx: typer.Context,
    prompt: list[str] | None = typer.Argument(
        None,
        help=(
            "Natural-language description of what to build, ask, plan, or "
            "document. If omitted, the CLI prints help."
        ),
    ),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    live: bool = typer.Option(
        False, "--live", help="Use the real provider chosen by the router (default: mock)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit a JSON summary."),
    save_diff: Path | None = typer.Option(
        None, "--save-diff", help="Write the produced diff to this path."
    ),
    no_commit: bool = typer.Option(
        False, "--no-commit", help="Skip the auto-commit step."
    ),
    no_tests: bool = typer.Option(
        False, "--no-tests", help="Skip the test stage."
    ),
) -> None:
    """Top-level Forge command: run the full pipeline on a free-form prompt."""
    if ctx.invoked_subcommand is not None:
        return
    if not prompt:
        # Typer will print help when no args are provided; we add a
        # tiny banner to make the entry point discoverable.
        get_console().print(
            "Usage: forge \"<your request>\"  -- see `forge --help`."
        )
        return
    text = " ".join(prompt).strip()
    asyncio.run(
        run_forge(
            text,
            Path(path).resolve(),
            live=live,
            json_output=json_output,
            save_diff=save_diff,
            no_commit=no_commit,
            no_tests=no_tests,
        )
    )


async def run_forge(
    text: str,
    path: Path,
    *,
    live: bool,
    json_output: bool,
    save_diff: Path | None,
    no_commit: bool,
    no_tests: bool,
) -> None:
    """Run the orchestrator on ``text`` and render the result.

    Public so the top-level ``main.py`` callback can call it; the
    internal Typer sub-app in :mod:`commands_forge` is still wired
    for forward-compatibility.
    """
    # When tests are disabled, pass a no-op test command so the
    # build workflow's test stage succeeds instantly.
    test_command = "true" if no_tests else None
    provider = _build_provider_for(live=live, cwd=path)
    _register_default_workflows(provider, test_command=test_command)
    orchestrator = Orchestrator(_REGISTRY, provider=provider)
    result = await orchestrator.run(text)

    if save_diff and result.diff:
        save_diff.write_text(result.diff, encoding="utf-8")
        info(f"Diff written to {save_diff}.")

    if json_output:
        payload = {
            "success": result.success,
            "intent": result.intent.value,
            "workflow": result.workflow,
            "duration_seconds": result.duration_seconds,
            "summary": result.summary,
            "files_touched": [str(p) for p in result.files_touched],
            "diff_length": len(result.diff),
            "error": result.error,
        }
        sys.stdout.write(json.dumps(payload, indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        render_result(result)

    # Auto-commit (unless disabled).
    if result.success and not no_commit and result.files_touched:
        _maybe_commit(path, result)

    if not result.success:
        error(result.error or "Forge pipeline failed.")
        raise typer.Exit(code=1)


def render_result(result) -> None:
    console = get_console()
    console.print()
    console.print(f"[bold]Intent:[/bold] {result.intent.value}")
    console.print(f"[bold]Workflow:[/bold] {result.workflow}")
    console.print(f"[bold]Duration:[/bold] {result.duration_seconds:.2f}s")
    console.print()
    if result.summary:
        console.print(result.summary)
    if result.files_touched:
        rel = [str(p) for p in result.files_touched]
        rows = [[p] for p in rel]
        table(["File"], rows, title=f"Files touched ({len(rel)})")
    if result.stages:
        rows = [
            [
                str(s.get("name", "?")),
                str(s.get("status", "?")),
                f"{float(s.get('duration_seconds') or 0.0):.3f}s",
                str(s.get("error") or "—"),
            ]
            for s in result.stages
        ]
        table(["Stage", "Status", "Duration", "Error"], rows, title="Pipeline stages")

    if result.success:
        success("Forge pipeline finished.")
    else:
        warn("Forge pipeline did not complete successfully.")


def _maybe_commit(project: Path, result) -> None:
    """Best-effort auto-commit: only if the user has not already committed
    these files and the project is a git repo.
    """
    try:
        diff = diff_staged(project)
    except GitRepoError as exc:
        warn(f"Skipping auto-commit: {exc}")
        return
    if not diff and result.diff:
        # Stage the touched files and let the user run `forge commit`.
        from forgecli.cli.commands_commit import _run_git

        for path in result.files_touched:
            _run_git(["add", str(path)], project)
        info("Touched files staged. Run `forge commit` to record the change.")
        return
    if diff:
        info("Staged changes detected; run `forge commit` to record them.")


__all__ = ["app", "get_registry", "render_result", "run_forge"]


# We expose the rich Typer sub-app as ``app`` (for compatibility) but
# the actual top-level `forge "<prompt>"` is wired in ``main.py`` via
# the ``run_forge`` helper below.
