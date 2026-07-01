"""``forge commit`` subcommand: AI-powered commit generator."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from forgecli.cli.ui import get_console
from forgecli.commit.git_utils import (
    GitRepoError,
    diff_staged,
    is_git_repo,
)

app = typer.Typer(
    help="AI-powered Conventional Commit generator.",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def commit_cmd(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root to run commit in."),
) -> None:
    """Generate a semantic commit message and create the commit."""
    if ctx.invoked_subcommand is not None:
        return

    import asyncio
    asyncio.run(run_commit_workflow(Path(path)))


async def run_commit_workflow(project_path: Path) -> None:
    from forgecli.cli.bootstrap import bootstrap_context, resolve_provider_and_decision
    from forgecli.optimizer.ponytail import PromptOptimizer
    from forgecli.providers.base import ChatMessage, ChatRequest, Role

    console = get_console()

    if not is_git_repo(project_path):
        console.print(f"[bold red]Error:[/bold red] {project_path} is not inside a git working tree.")
        raise typer.Exit(code=1)

    diff = diff_staged(project_path)
    if not diff.strip():
        console.print("No staged changes found.\nRun:\n  git add <files>\nbefore using forge commit.")
        raise typer.Exit(code=1)

    prompt = (
        "Analyze the following git diff and generate a concise Conventional Commit message. "
        "It must follow the conventional commits specification: start with a type (e.g., feat, fix, docs, style, refactor, perf, test, chore, build, ci), optional scope, and a short description. "
        "Then, optionally add a list of bullet points outlining the changes. "
        "Output ONLY the raw commit message text. Do not include markdown block quotes, fences, backticks, or any other explanations.\n\n"
        f"Git Diff:\n{diff}"
    )

    # Ponytail optimization
    app_context = bootstrap_context(cwd=project_path)
    optimizer = app_context.container.resolve(PromptOptimizer)  # type: ignore[type-abstract]
    request = ChatRequest(
        messages=[ChatMessage(role=Role.USER, content=prompt)],
    )
    optimized = await optimizer.optimize_chat(request)
    optimized_prompt = optimized.request.messages[0].content

    # LLM Call
    provider, decision = resolve_provider_and_decision(live=True, cwd=project_path)
    commit_request = ChatRequest(
        model=decision.model if decision else None,
        messages=[
            ChatMessage(
                role=Role.SYSTEM,
                content="You are a senior software engineer specialized in creating concise Conventional Commit messages."
            ),
            ChatMessage(role=Role.USER, content=optimized_prompt),
        ],
    )

    response = await provider.chat(commit_request)
    commit_message = response.message.content.strip()

    if commit_message.startswith("```"):
        lines = commit_message.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        commit_message = "\n".join(lines).strip()

    console.print("────────────────────────────────────────\n")
    console.print("[bold yellow]AI Generated Commit Message[/bold yellow]\n")
    console.print(commit_message)
    console.print("\n────────────────────────────────────────\n")
    console.print("Press Enter to commit")
    console.print("Press Ctrl+C to cancel")

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Commit cancelled.[/yellow]")
        raise typer.Exit(code=1) from None

    try:
        _run_git(["commit", "-m", commit_message], project_path)
    except GitRepoError as exc:
        console.print(f"[bold red]Error committing changes:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold green]✓ Commit created successfully.[/bold green]")


def _run_git(args: list[str], project: Path) -> str:
    """Run a git command and return stdout, raising on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(project),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitRepoError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or 'unknown error'}"
        )
    return result.stdout


__all__ = ["_run_git", "app"]
