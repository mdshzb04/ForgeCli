"""``forge commit`` subcommand: AI-powered commit generator."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from forgecli.cli.ui import get_console
from forgecli.commit.git_utils import (
    GitRepoError,
    current_branch,
    diff_staged,
    is_git_repo,
    status_porcelain,
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


def get_staged_stats(project_path: Path) -> dict[str, int]:
    lines = status_porcelain(project_path)
    modified = 0
    added = 0
    deleted = 0
    for line in lines:
        if len(line) < 2:
            continue
        x = line[0]
        # X is the status of the index (staged)
        if x in ('M', 'R'):
            modified += 1
        elif x in ('A', 'C'):
            added += 1
        elif x == 'D':
            deleted += 1
    return {"modified": modified, "added": added, "deleted": deleted}


async def run_commit_workflow(project_path: Path) -> None:
    from rich.box import ROUNDED
    from rich.panel import Panel
    from rich.text import Text

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

    # Ponytail optimization (run silently in background)
    app_context = bootstrap_context(cwd=project_path)
    optimizer = app_context.container.resolve(PromptOptimizer)  # type: ignore[type-abstract]
    request = ChatRequest(
        messages=[ChatMessage(role=Role.USER, content=prompt)],
    )
    optimized = await optimizer.optimize_chat(request)
    optimized_prompt = optimized.request.messages[0].content

    # LLM Call
    provider, decision = resolve_provider_and_decision(live=True, cwd=project_path)

    # Bypass OptimizedProvider wrapper to prevent Ponytail rules from rewriting/compressing the final commit message
    raw_provider = provider._base if hasattr(provider, "_base") else provider


    commit_request = ChatRequest(
        model=decision.model if decision else None,
        messages=[
            ChatMessage(
                role=Role.SYSTEM,
                content=(
                    "You are a senior software engineer specialized in creating concise Conventional Commit messages. "
                    "Write clean, human-quality Conventional Commits like experienced maintainers. "
                    "Do NOT write Ponytail/YAGNI summaries, rules, or optimization choices. "
                    "Focus only on describing the actual codebase changes.\n\n"
                    "Format example:\n"
                    "feat(cli): improve build workflow output\n\n"
                    "- redesign build result UI\n"
                    "- add syntax-highlighted code previews\n"
                    "- simplify offline mode messaging\n"
                    "- improve CLI presentation\n\n"
                    "Output ONLY the raw commit message. Do not include markdown fences, backticks, or any explanation."
                )
            ),
            ChatMessage(role=Role.USER, content=optimized_prompt),
        ],
    )

    response = await raw_provider.chat(commit_request)
    commit_message = response.message.content.strip()

    if commit_message.startswith("```"):
        lines = commit_message.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        commit_message = "\n".join(lines).strip()

    repo_name = project_path.resolve().name
    branch_name = current_branch(project_path)
    stats = get_staged_stats(project_path)

    parts = []
    if stats["modified"] > 0:
        parts.append(f"{stats['modified']} modified")
    if stats["added"] > 0:
        parts.append(f"{stats['added']} added")
    if stats["deleted"] > 0:
        parts.append(f"{stats['deleted']} deleted")
    stats_str = " • ".join(parts) if parts else "0 modified • 0 added • 0 deleted"

    # Display the message inside a beautiful Rich panel with repo, branch, and changed files
    preview_text = Text()
    preview_text.append("Repository  ", style="bold cyan")
    preview_text.append(f"{repo_name}\n", style="white")
    preview_text.append("Branch      ", style="bold cyan")
    preview_text.append(f"{branch_name}\n", style="white")
    preview_text.append("Files       ", style="bold cyan")
    preview_text.append(f"{stats_str}\n\n", style="white")
    preview_text.append("────────────────────────────────────────\n\n", style="dim")
    preview_text.append(commit_message, style="white")

    panel = Panel(
        preview_text,
        title="[bold yellow]AI Commit Preview[/bold yellow]",
        border_style="cyan",
        box=ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)
    console.print()
    console.print("Press [bold green]Enter[/bold green] to commit")
    console.print("Press [bold red]Ctrl+C[/bold red] to cancel")

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

    # After committing, show post-commit details
    try:
        commit_hash = _run_git(["rev-parse", "HEAD"], project_path).strip()
        short_hash = commit_hash[:7]
    except Exception:
        short_hash = "unknown"

    console.print()
    summary_text = Text()
    summary_text.append("Repository\n", style="bold cyan")
    summary_text.append(f"{repo_name}\n\n", style="white")
    summary_text.append("Branch\n", style="bold cyan")
    summary_text.append(f"{branch_name}\n\n", style="white")
    summary_text.append("Files\n", style="bold cyan")
    summary_text.append(f"{stats_str}\n\n", style="white")
    summary_text.append("  - [bold green]✓ Commit Created[/bold green]\n")
    summary_text.append(f"  - [bold]Commit hash:[/bold] {short_hash}\n")
    summary_text.append(f"  - [bold]Branch:[/bold] {branch_name}\n")
    summary_text.append(f"  - [bold]Commit message:[/bold] {commit_message.splitlines()[0]}\n")
    summary_text.append("  - [bold yellow]Tip:[/bold yellow] `git push`")

    post_panel = Panel(
        summary_text,
        title="[bold green]Commit Success[/bold green]",
        border_style="green",
        box=ROUNDED,
        padding=(1, 2),
    )
    console.print(post_panel)


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
