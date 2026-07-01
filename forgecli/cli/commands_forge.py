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

from forgecli.cli.ui import error, get_console, info, table, warn
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
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    provider, _ = resolve_provider_and_decision(live=live, cwd=cwd)
    return provider


def _build_orchestrator_for(
    *,
    live: bool,
    cwd: Path,
) -> Orchestrator:
    """Backwards-compatible shim that returns an :class:`Orchestrator`."""
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    provider, decision = resolve_provider_and_decision(live=live, cwd=cwd)
    _register_default_workflows(provider)
    return build_orchestrator(_REGISTRY, provider=provider, decision=decision)


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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    diff: bool = typer.Option(False, "--diff", "-d", help="Show unified git diff."),
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
            verbose=verbose,
            diff=diff,
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
    verbose: bool = False,
    diff: bool = False,
) -> None:
    """Run the orchestrator on ``text`` and render the result.

    Public so the top-level ``main.py`` callback can call it; the
    internal Typer sub-app in :mod:`commands_forge` is still wired
    for forward-compatibility.
    """
    # When tests are disabled, pass a no-op test command so the
    # build workflow's test stage succeeds instantly.
    test_command = "true" if no_tests else None
    from forgecli.cli.bootstrap import resolve_provider_and_decision
    provider, decision = resolve_provider_and_decision(live=live, cwd=path)
    if not live and not json_output:
        console = get_console()
        console.print("[yellow]⚠ Offline Mode[/yellow]\n")
        console.print("Using Forge's built-in mock AI.\n")
        console.print("Run:\n")
        console.print("  forge --live \"<prompt>\"\n")
        console.print("to use your configured provider.\n")
    _register_default_workflows(provider, test_command=test_command)
    orchestrator = Orchestrator(_REGISTRY, provider=provider, decision=decision)
    result = await orchestrator.run(text)

    if save_diff and result.diff:
        save_diff.write_text(result.diff, encoding="utf-8")
        if verbose:
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
        render_result(result, verbose=verbose, diff=diff)

    # Auto-commit (unless disabled).
    if result.success and not no_commit and result.files_touched:
        _maybe_commit(path, result)

    if not result.success:
        error(result.error or "Forge pipeline failed.")
        raise typer.Exit(code=1)


def render_result(result, verbose: bool = False, diff: bool = False) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.syntax import Syntax

    from forgecli.cli.commands_build import get_display_changes, get_lexer

    console = get_console()

    if not verbose:
        if result.success:
            console.print("[bold green]✓ Forge completed[/bold green]\n")
        else:
            if result.diff:
                console.print("[bold orange3]⚠ Couldn't automatically apply the generated changes.[/bold orange3]\n")
                console.print("The generated code is shown below.\n")
            else:
                console.print("[bold red]✗ Forge failed[/bold red]\n")

        console.print("────────────────────────────────────────────\n")

        changes = get_display_changes(result.diff)
        if changes:
            console.print("Created Files\n")
        for chg in changes:
            path = chg["path"]
            content = chg["content"]
            status = chg["status"]

            console.print(f"📄 {path}\n")
            lexer = get_lexer(path)
            syntax = Syntax(content.rstrip(), lexer, theme="monokai")
            panel = Panel(
                syntax,
                border_style="orange3",
                box=box.ROUNDED,
                expand=False,
            )
            console.print(panel)
            console.print()

            line_count = len(content.splitlines())
            console.print(f"{status} {path}")
            console.print(f"{line_count} lines generated.\n")

        if result.summary and result.workflow not in ("build", "legacy"):
            from rich.markdown import Markdown
            console.print(Markdown(result.summary.strip()))
            console.print()

        console.print(f"Completed in {result.duration_seconds:.1f} s\n")
        return

    # Verbose Mode
    console.print("────────────────────────────────────────\n")
    if result.success:
        console.print("[bold green]✓ Forge completed[/bold green]\n")
    else:
        console.print("[bold red]✗ Forge failed[/bold red]\n")

    if result.diff:
        console.print("[bold cyan]Unified Diff:[/bold cyan]\n")
        console.print(result.diff)
        console.print()

    # Try to find provider name
    provider_name = "mock"
    if result.extras and result.extras.get("decision"):
        provider_name = result.extras["decision"].provider_name

    provider_map = {
        "mock": "Mock (Offline)",
        "openai": "OpenAI (Live)",
        "anthropic": "Anthropic (Live)",
        "google": "Gemini (Live)",
        "gemini": "Gemini (Live)",
    }
    provider_str = provider_map.get(provider_name.lower(), f"{provider_name.title()} (Live)")

    if result.summary and result.workflow not in ("build", "legacy"):
        from rich.markdown import Markdown
        console.print(Markdown(result.summary.strip()))
        console.print()

    console.print("[bold]Intent[/bold]")
    console.print(result.intent.value)
    console.print()
    console.print("[bold]Workflow[/bold]")
    console.print(result.workflow)
    console.print()
    console.print("[bold]Provider[/bold]")
    console.print(provider_str)
    console.print()

    console.print("[bold]Time[/bold]")
    console.print(f"{result.duration_seconds:.1f} seconds")
    console.print()

    if result.stages:
        console.print("[bold yellow]=== Pipeline Stages timings ===[/bold yellow]\n")
        rows = []
        for s in result.stages:
            rows.append([
                str(s.get("name", "Stage")),
                str(s.get("status", "succeeded")),
                f"{float(s.get('duration_seconds') or 0.0):.3f}s",
                str(s.get("error") or "—")
            ])
        table(["Stage", "Status", "Duration", "Error"], rows, title="Pipeline stages")
        console.print()

    console.print("────────────────────────────────────────")


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
