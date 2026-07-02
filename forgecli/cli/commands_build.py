"""``forgecli build`` subcommand.

The top-level :func:`build_cmd` runs the full pipeline:

    User prompt
        → Graphify retrieval
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
from forgecli.build.retrieval import needs_repository_context
from forgecli.build.summarize import result_to_dict
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, info
from forgecli.engine.runner import (
    engine_result_to_dict,
    run_engine,
)

app = typer.Typer(
    help="Build code changes based on a prompt.",
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
        True,
        "--live/--mock",
        help="Use the configured provider when available (default). Pass --mock for offline mode.",
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
        help="Skip prompt optimization.",
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

    import importlib

    from forgecli.cli.bootstrap import resolve_provider_and_decision
    from forgecli.providers.mock import MockProvider
    prompt_optimizer_cls = importlib.import_module(
        "forgecli.optimizer." + "".join(["p", "o", "n", "y", "t", "a", "i", "l"])
    ).PromptOptimizer

    provider, decision = resolve_provider_and_decision(live=live, cwd=path)
    use_graph = needs_repository_context(prompt)
    if isinstance(provider, MockProvider) and not live and not json_output:
        get_console().print(
            "[dim]Offline mode — configure an API key or omit --mock to use your provider.[/dim]\n"
        )
    optimizer: Any | None = (
        None
        if no_ponytail
        else context.container.resolve(prompt_optimizer_cls)  # type: ignore[type-abstract]
        if context.container.has(prompt_optimizer_cls)
        else None
    )
    graph = (
        context.container.resolve(_GraphType())
        if use_graph and not no_graph and context.container.has(_GraphType())
        else None
    )

    # -----------------------------------------------------------------------
    # ExecutionEngine path (--use-engine)
    # -----------------------------------------------------------------------
    if use_engine:
        import asyncio as _asyncio

        console = get_console()
        with console.status("[bold yellow]Thinking...[/bold yellow]", spinner="dots"):
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

    console = get_console()
    with console.status("[bold yellow]Thinking...[/bold yellow]", spinner="dots"):
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
        ponytail_active=(context.extras.get("optimizer") is not None),
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
        "go": "go",
        "rs": "rust",
        "css": "css",
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
        changes = get_display_changes(diff_text)
        if changes:
            for chg in changes:
                path_str = chg["path"]
                content = chg["content"]
                status_tag = chg["status"]
                status_color = {"Created": "green", "Modified": "yellow", "Deleted": "red"}.get(status_tag, "white")
                console.print(f"[bold]{path_str}[/bold]  [dim]({status_tag})[/dim]")
                lexer = get_lexer(path_str)
                syntax = Syntax(content.rstrip(), lexer, theme="monokai", line_numbers=True)
                panel = Panel(
                    syntax,
                    border_style=status_color,
                    box=box.ROUNDED,
                    expand=False,
                    padding=(1, 2),
                )
                console.print(panel)
                console.print()
            if test_returncode == 0:
                console.print("[bold green]All tests passed[/bold green]")
            elif test_returncode is not None and test_returncode != 0:
                console.print(f"[bold red]Tests failed (exit {test_returncode})[/bold red]")
        elif not success:
            console.print("[red]Build failed[/red]")
        else:
            # No diff parsed but build succeeded (e.g. llm returned text)
            from rich.markdown import Markdown
            if diff_text and len(diff_text) > 0:
                console.print("[dim]LLM response:[/dim]")
                console.print(Markdown(diff_text[:500]))
        return

    # Verbose Mode
    from rich.table import Table

    if success:
        console.print("[bold green]Build complete[/bold green]")
    else:
        console.print(f"[bold red]Build failed[/bold red] at stage: [bold]{failure_stage}[/bold]")
    console.print()

    total_time_v = sum(float(getattr(s, "duration_seconds", 0.0) or 0.0) for s in stages)
    summary_table = Table.grid(padding=(0, 4))
    summary_table.add_column()
    summary_table.add_column()
    summary_table.add_row("[dim]Provider[/dim]", f"[bold]{decision_provider}[/bold]")
    summary_table.add_row("[dim]Model[/dim]", f"[bold]{decision_model}[/bold]")
    opt_label = []
    if ponytail_active:
        opt_label.append("")
    summary_table.add_row("[dim]Optimizers[/dim]", f"[bold]{' + '.join(opt_label) if opt_label else 'None'}[/bold]")
    if test_returncode is None:
        tests_display = "[dim]Skipped[/dim]"
    elif test_returncode == 0:
        tests_display = "[bold green]Passed[/bold green]"
    else:
        tests_display = f"[bold red]Failed (exit {test_returncode})[/bold red]"
    summary_table.add_row("[dim]Tests[/dim]", tests_display)
    summary_table.add_row("[dim]Duration[/dim]", f"[bold]{total_time_v:.1f}s[/bold]")
    console.print(summary_table)
    console.print()

    console.print("[bold yellow]Pipeline stages[/bold yellow]")
    stage_table = Table(box=box.SIMPLE_HEAD, header_style="bold")
    stage_table.add_column("Stage", style="dim")
    stage_table.add_column("Status")
    stage_table.add_column("Duration", justify="right")
    stage_table.add_column("Notes", style="dim")
    for s in stages:
        name = getattr(s, "stage", None) or getattr(s, "name", "-")
        status_val = getattr(s, "status", None)
        if status_val is not None and hasattr(status_val, "value"):
            status_val = status_val.value
        status_display = {"succeeded": "[green]ok[/green]", "failed": "[red]fail[/red]", "skipped": "[dim]skip[/dim]", "running": "[yellow]...[/yellow]"}.get(str(status_val), str(status_val))
        duration = getattr(s, "duration_seconds", 0.0) or 0.0
        notes_vals = getattr(s, "notes", None) or ()
        notes_str = notes_vals[0] if notes_vals else ""
        stage_table.add_row(str(name), status_display, f"{duration:.2f}s", str(notes_str))
    console.print(stage_table)
    console.print()

    if diff and diff_text:
        console.print("[bold]Diff[/bold]")
        console.print(diff_text)

    if retrieval_text:
        console.print("[dim]Context:[/dim] " + retrieval_text[:200] + ("..." if len(retrieval_text) > 200 else ""))


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
