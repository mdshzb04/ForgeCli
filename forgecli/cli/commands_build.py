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

import typer

from forgecli.build import BuildPipeline, BuildResult
from forgecli.build.pipeline import build_context_from, default_pipeline
from forgecli.build.summarize import result_to_dict
from forgecli.builder.builder import Builder
from forgecli.builder.builder import BuildResult as LegacyBuildResult
from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, info, success, table
from forgecli.optimizer.ponytail import PromptOptimizer
from forgecli.providers.base import Provider, ProviderRegistry
from forgecli.providers.mock import MockProvider, MockProviderConfig
from forgecli.providers.router import ModelRouter
from forgecli.providers.router_state import load_state
from forgecli.utils.paths import ProjectPaths

app = typer.Typer(
    help="Run the build pipeline (Graphify → Ponytail → LLM → apply → test → summarize).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# ---------------------------------------------------------------------------
# forge build "<prompt>"
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
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
) -> None:
    context = bootstrap_context(cwd=str(path))
    paths: ProjectPaths = context.paths
    target = path.resolve()

    router: ModelRouter = context.container.resolve(ModelRouter)
    state = load_state(paths.data_dir / "router.json")
    decision = router.select(state.choice)
    if not live:
        info("Offline mode: using the mock provider. Pass --live to use the real one.")
        provider: Provider = MockProvider(MockProviderConfig())
        decision = type(decision)(
            provider_name=provider.name,
            model=decision.model,
            mode=decision.mode,
            cost_in=0.0,
            cost_out=0.0,
        )
    else:
        registry: ProviderRegistry = context.container.resolve(ProviderRegistry)
        try:
            provider = registry.create(decision.provider_name, _config_for(decision.provider_name))
        except Exception as exc:
            error(f"Could not build provider: {exc}")
            raise typer.Exit(code=1) from exc
    optimizer: PromptOptimizer | None = (
        None
        if no_ponytail
        else context.container.resolve(PromptOptimizer)
        if context.container.has(PromptOptimizer)
        else None
    )
    graph = (
        context.container.resolve(_GraphType())
        if not no_graph and context.container.has(_GraphType())
        else None
    )

    build_context = build_context_from(
        prompt,
        root=target,
        router=router,
        state=state,
    )
    # Re-resolve the decision after we've decided on live vs mock.
    build_context.decision = decision

    pipeline: BuildPipeline = default_pipeline(
        provider=provider,
        optimizer=optimizer,
        graph=graph,
        test_command=None if no_tests else test_command,
    )
    if retries:
        build_context.extras["retries"] = retries

    result: BuildResult = await pipeline.run(build_context)

    if save_diff is not None and build_context.diff_text:
        save_diff.write_text(build_context.diff_text, encoding="utf-8")
        info(f"Diff written to {save_diff}")

    if json_output:
        sys.stdout.write(json.dumps(result_to_dict(result), indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    _render(result)


def _render(result: BuildResult) -> None:
    context = result.context
    console = get_console()
    if context.summary:
        console.print(context.summary)
    console.print()
    rows: list[list[str]] = []
    for record in context.stages:
        rows.append(
            [
                record.name,
                record.status.value,
                f"{(record.duration_seconds or 0):.3f}s",
                record.error or "—",
            ]
        )
    table(["Stage", "Status", "Duration", "Error"], rows, title="Pipeline stages")
    if result.success:
        success("Build pipeline finished.")
    else:
        error(f"Build failed at stage: {result.failure_stage}")


# ---------------------------------------------------------------------------
# Backwards-compatible `forge build run`
# ---------------------------------------------------------------------------


@app.command("run")
def run() -> None:
    """Run a placeholder build pipeline (legacy)."""
    builder = Builder()
    result: LegacyBuildResult = builder.build(edits=[])
    get_console().print(result)
    success("Build complete (placeholder).")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
