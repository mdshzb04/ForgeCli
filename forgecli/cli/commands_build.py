"""``forgecli build`` subcommand.

The top-level :func:`build_cmd` runs the full pipeline:

    User prompt
        → Graphify retrieval
        → Ponytail optimization
        → LLM call
        → Diff extraction
        → Apply diff
        → Run tests
        → Summarize

By default the LLM is the offline :class:`MockProvider`; pass
``--live`` to use the real provider chosen by the router.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer

from forgecli.build import BuildPipeline, BuildResult
from forgecli.build.pipeline import build_context_from, default_pipeline
from forgecli.build.summarize import result_to_dict
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, info, table
from forgecli.engine.runner import (
    engine_result_to_dict,
    run_engine,
)
from forgecli.optimizer.ponytail import PromptOptimizer

app = typer.Typer(
    help="Run the build pipeline (Graphify → Ponytail → LLM → apply → test → summarize).",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"allow_interspersed_args": True},
)


# ---------------------------------------------------------------------------
# forge build "<prompt>"
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True, context_settings={"allow_interspersed_args": True})
def build_cmd(
    ctx: typer.Context,
    prompt: str = typer.Argument(..., help="Natural-language description of the change to make."),
    path: str = typer.Option(".", "--path", "-p", help="Project root."),
    live: bool = typer.Option(
        False,
        "--live",
        help="Use the real provider chosen by the router (default: offline mock).",
    ),
    test_command: str | None = typer.Option(
        None,
        "--test-command",
        help="Override the test command (default: 'pytest -q').",
    ),
    no_tests: bool = typer.Option(False, "--no-tests", help="Skip the test stage."),
    no_graph: bool = typer.Option(False, "--no-graph", help="Skip Graphify retrieval."),
    no_ponytail: bool = typer.Option(
        False,
        "--no-ponytail",
        help="Skip the Ponytail prompt-optimizer stage.",
    ),
    retries: int = typer.Option(
        0,
        "--retries",
        help="Retry the LLM stage up to N times on transient failures.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    save_diff: Path | None = typer.Option(
        None,
        "--save-diff",
        help="Write the extracted diff to this path (for inspection).",
    ),
    use_engine: bool = typer.Option(
        False,
        "--use-engine",
        help="Use the new ExecutionEngine pipeline (default: legacy BuildPipeline).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    diff: bool = typer.Option(False, "--diff", "-d", help="Show unified git diff."),
) -> None:
    """Run the full pipeline on ``prompt``."""
    if ctx.invoked_subcommand is not None:
        return

    asyncio.run(
        _run_build(
            prompt=prompt,
            path=Path(path),
            live=live,
            test_command=test_command,
            no_tests=no_tests,
            no_graph=no_graph,
            no_ponytail=no_ponytail,
            retries=retries,
            json_output=json_output,
            save_diff=save_diff,
            use_engine=use_engine,
            verbose=verbose,
            diff=diff,
        )
    )


async def _run_build(
    *,
    prompt: str,
    path: Path,
    live: bool,
    test_command: str | None,
    no_tests: bool,
    no_graph: bool,
    no_ponytail: bool,
    retries: int,
    json_output: bool,
    save_diff: Path | None,
    use_engine: bool = False,
    verbose: bool = False,
    diff: bool = False,
) -> None:
    context = bootstrap_context(cwd=str(path))
    target = path.resolve()

    from forgecli.cli.bootstrap import resolve_provider_and_decision
    provider, decision = resolve_provider_and_decision(live=live, cwd=path)
    if not live and not json_output:
        console = get_console()
        console.print("[yellow]⚠ Offline Mode[/yellow]\n")
        console.print("Using Forge's built-in mock AI.\n")
        console.print("Run:\n")
        console.print("  forge build --live\n")
        console.print("to use your configured provider.\n")
    optimizer: PromptOptimizer | None = (
        None
        if no_ponytail
        else context.container.resolve(PromptOptimizer)  # type: ignore[type-abstract]
        if context.container.has(PromptOptimizer)
        else None
    )
    graph = (
        context.container.resolve(_GraphType())
        if not no_graph and context.container.has(_GraphType())
        else None
    )

    # -----------------------------------------------------------------------
    # ExecutionEngine path (--use-engine)
    # -----------------------------------------------------------------------
    if use_engine:
        import asyncio as _asyncio

        # run_engine is synchronous (calls asyncio.run internally); we must
        # run it in a thread to avoid "cannot run nested event loop" errors
        # when we're already inside asyncio.run from build_cmd.
        loop = _asyncio.get_event_loop()
        eng_result = await loop.run_in_executor(
            None,
            lambda: run_engine(
                prompt,
                target,
                provider=provider,
                optimizer=optimizer,
                graph=graph,
                test_command=None if no_tests else test_command,
                retries=retries,
                skip_tests=no_tests,
                skip_graph=no_graph,
                skip_ponytail=no_ponytail,
            ),
        )
        if save_diff is not None and eng_result.context.diff_text:
            save_diff.write_text(eng_result.context.diff_text, encoding="utf-8")
            if verbose:
                info(f"Diff written to {save_diff}")
        if json_output:
            sys.stdout.write(json.dumps(engine_result_to_dict(eng_result), indent=2))
            sys.stdout.write("\n")
            sys.stdout.flush()
            return

        render_pipeline_result(
            success=eng_result.success,
            prompt=prompt,
            diff_text=eng_result.context.diff_text,
            applied_files=eng_result.context.applied_files,
            stages=eng_result.context.log,
            decision_provider=eng_result.context.model_selection.provider if eng_result.context.model_selection else "mock",
            decision_model=eng_result.context.model_selection.model if eng_result.context.model_selection else "",
            optimized_notes=list(eng_result.context.optimized_notes),
            ponytail_active=not no_ponytail,
            test_returncode=eng_result.context.test_returncode,
            failure_stage=eng_result.failed_stage,
            retrieval_text=eng_result.context.retrieval.context_text if eng_result.context.retrieval else "",
            internal_summary="",
            verbose=verbose,
            diff=diff,
        )
        if not eng_result.success:
            raise typer.Exit(code=1)
        return

    # -----------------------------------------------------------------------
    # Legacy BuildPipeline path (default)
    # -----------------------------------------------------------------------
    build_context = build_context_from(
        prompt,
        root=target,
    )
    # Re-resolve the decision after we've decided on live vs mock.
    build_context.decision = decision

    pipeline: BuildPipeline = default_pipeline(
        provider=provider,
        optimizer=optimizer,
        graph=graph,
        test_command=test_command,
        skip_tests=no_tests,
    )
    if retries:
        build_context.extras["retries"] = retries

    result: BuildResult = await pipeline.run(build_context)

    if save_diff is not None and build_context.diff_text:
        save_diff.write_text(build_context.diff_text, encoding="utf-8")
        if verbose:
            info(f"Diff written to {save_diff}")

    if json_output:
        sys.stdout.write(json.dumps(result_to_dict(result), indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    _render(result, verbose=verbose, diff=diff)


def _render(result: BuildResult, verbose: bool = False, diff: bool = False) -> None:
    context = result.context
    render_pipeline_result(
        success=result.success,
        prompt=context.prompt,
        diff_text=context.diff_text,
        applied_files=context.applied_files,
        stages=context.stages,
        decision_provider=context.decision.provider_name if context.decision else "mock",
        decision_model=context.decision.model if context.decision else "",
        optimized_notes=list(context.optimized_notes),
        ponytail_active=context.decision is not None,  # Ponytail is active if we optimized
        test_returncode=context.test_returncode,
        failure_stage=result.failure_stage,
        retrieval_text=context.retrieval,
        internal_summary=context.summary,
        verbose=verbose,
        diff=diff,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_lexer(path_str: str) -> str:
    name = path_str.split("/")[-1] if "/" in path_str else path_str
    ext = name.split(".")[-1].lower() if "." in name else ""

    mapping = {
        "html": "html",
        "htm": "html",
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "json": "json",
        "yaml": "yaml",
        "yml": "yaml",
        "md": "markdown",
        "toml": "toml",
    }
    return mapping.get(ext, "text")


def get_display_changes(diff_text: str) -> list[dict]:
    from forgecli.build.apply import parse_unified_diff

    try:
        parsed_files = parse_unified_diff(diff_text)
    except Exception:
        return []

    results = []
    blocks = diff_text.split("diff --git ")

    for parsed in parsed_files:
        path = parsed.path
        status = "Modified"
        for block in blocks:
            if f"b/{path}" in block or f"/{path}" in block:
                if "new file" in block or "/dev/null" in block:
                    status = "Created"
                elif "deleted file" in block:
                    status = "Deleted"
                break

        results.append({
            "path": path,
            "status": status,
            "content": parsed.new_content
        })
    return results


def render_pipeline_result(
    *,
    success: bool,
    prompt: str,
    diff_text: str,
    applied_files: list[Path],
    stages: list[Any],
    decision_provider: str,
    decision_model: str,
    optimized_notes: list[str],
    ponytail_active: bool,
    test_returncode: int | None,
    failure_stage: str | None,
    retrieval_text: str,
    internal_summary: str,
    verbose: bool,
    diff: bool,
) -> None:
    from rich import box
    from rich.panel import Panel
    from rich.syntax import Syntax

    console = get_console()

    if not verbose:
        # Clean / Minimal Mode
        if success:
            console.print("[bold green]✓ Build completed[/bold green]\n")
        else:
            if diff_text:
                console.print("[bold orange3]⚠ Generated successfully[/bold orange3]\n")
                console.print("Could not automatically apply changes.\n")
                console.print("The generated files are shown below.\n")
            else:
                console.print("[bold red]✗ Build failed[/bold red]\n")

        console.print("────────────────────────────────────────────\n")

        changes = get_display_changes(diff_text)
        for chg in changes:
            path = chg["path"]
            content = chg["content"]

            console.print(f"[bold orange3]{path}[/bold orange3]\n")
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

        total_time = sum(float(getattr(s, "duration_seconds", 0.0) or 0.0) for s in stages)
        console.print(f"Time: {total_time:.1f} s\n")
        return

    # Verbose Mode
    console.print("────────────────────────────────────────\n")
    if success:
        console.print("[bold green]✓ Build completed[/bold green]\n")
    else:
        console.print("[bold red]✗ Build failed[/bold red]\n")
        if failure_stage:
            console.print(f"Failed at stage: [bold red]{failure_stage}[/bold red]\n")

    # Print the files in verbose or diff mode
    if diff_text:
        console.print("[bold cyan]Unified Diff:[/bold cyan]\n")
        console.print(diff_text)
        console.print()

    # Print summary
    provider_map = {
        "mock": "Mock (Offline)",
        "openai": "OpenAI (Live)",
        "anthropic": "Anthropic (Live)",
        "google": "Gemini (Live)",
        "gemini": "Gemini (Live)",
    }
    provider_str = provider_map.get(decision_provider.lower(), f"{decision_provider.title()} (Live)")
    optimizer_str = "Ponytail (Ultra)" if ponytail_active else "None"

    if test_returncode is None:
        tests_str = "Skipped"
    elif test_returncode == 0:
        tests_str = "[bold green]✓ Passed[/bold green]"
    else:
        tests_str = f"[bold red]✗ Failed (exit {test_returncode})[/bold red]"

    total_time = sum(float(getattr(s, "duration_seconds", 0.0) or 0.0) for s in stages)

    console.print("[bold]Provider[/bold]")
    console.print(provider_str)
    console.print()
    console.print("[bold]Optimizer[/bold]")
    console.print(optimizer_str)
    console.print()
    console.print("[bold]Tests[/bold]")
    console.print(tests_str)
    console.print()
    console.print("[bold]Time[/bold]")
    console.print(f"{total_time:.1f} seconds")
    console.print()

    if verbose:
        console.print("[bold yellow]=== Pipeline Stages timings ===[/bold yellow]\n")
        rows: list[list[str]] = []
        for s in stages:
            name = getattr(s, "stage", None) or getattr(s, "name", "Stage")
            status_val = getattr(s, "status", None)
            if status_val is not None and hasattr(status_val, "value"):
                status_val = status_val.value  # type: ignore[union-attr]
            duration = getattr(s, "duration_seconds", 0.0) or 0.0
            err = getattr(s, "error", None) or "—"
            rows.append([str(name), str(status_val), f"{duration:.3f}s", str(err)])
        table(["Stage", "Status", "Duration", "Error"], rows, title="Pipeline stages")
        console.print()

        if retrieval_text:
            console.print("[bold]Graph Retrieval Details:[/bold]")
            console.print(retrieval_text)
            console.print()

        if optimized_notes:
            console.print("[bold]Ponytail Optimization Details:[/bold]")
            for note in optimized_notes:
                console.print(f"  - {note}")
            console.print()

        if decision_provider:
            console.print("[bold]Provider Routing:[/bold]")
            console.print(f"  Provider: {decision_provider}")
            console.print(f"  Model: {decision_model}")
            console.print()

        if applied_files:
            console.print("[bold]Files touched:[/bold]")
            for f in applied_files:
                console.print(f"  - {f}")
            console.print()

        if diff_text:
            console.print("[bold]Diff Extraction:[/bold]")
            console.print(f"  Diff length: {len(diff_text)} chars")
            console.print()

        if internal_summary:
            console.print("[bold]Internal Diagnostics:[/bold]")
            console.print(internal_summary)
            console.print()

    console.print("────────────────────────────────────────")


def _GraphType():
    from forgecli.graph.repository import RepositoryGraph

    return RepositoryGraph


def _config_for(provider_name: str):
    """Build the right config dataclass for a real provider."""
    if provider_name == "openai":
        from forgecli.providers.openai import OpenAIConfig

        return OpenAIConfig()
    if provider_name == "anthropic":
        from forgecli.providers.anthropic import AnthropicConfig

        return AnthropicConfig()
    if provider_name == "google":
        from forgecli.providers.google import GeminiConfig

        return GeminiConfig()
    return None


__all__ = ["app"]
