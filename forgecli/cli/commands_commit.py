"""``forge commit`` subcommand: ultra-fast AI-powered commit generator.

Bypasses Caveman, , Graphify, and all prompt optimization.
Reads only the staged git diff, sends it to the configured model
with a minimal system prompt, generates a Conventional Commit message,
previews it, requests confirmation, then commits.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path

import typer
from rich.box import ROUNDED
from rich.panel import Panel
from rich.text import Text

from forgecli.cli.ui import get_console
from forgecli.commit.git_utils import (
    GitRepoError,
    current_branch,
    diff_staged,
    is_git_repo,
    status_porcelain,
)
from forgecli.providers.base import ChatMessage, ChatRequest, Role

app = typer.Typer(
    help="AI-powered Conventional Commit generator.",
    rich_markup_mode="rich",
)

_COMMIT_SYSTEM_PROMPT = (
    "Write a Conventional Commit message. "
    "Type: feat, fix, docs, refactor, perf, test, chore, build, ci. "
    "Optional scope in parens. Subject line under 72 chars. "
    "Blank line, then bullet list of changes. "
    "Output ONLY the commit message, no explanation."
)


def _resolve_provider_for_commit() -> tuple[str, str, str]:
    """Quick provider resolution — no DI container, no bootstrap.

    Returns (provider_name, model, api_key_env).
    """
    for name, env_var in [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("google", "GOOGLE_API_KEY"),
    ]:
        if os.environ.get(env_var):
            model = {"openai": "gpt-4o-mini", "anthropic": "claude-haiku-4.5", "google": "gemini-2.5-flash"}[name]
            return name, model, env_var

    from forgecli.core.credentials import get_api_key
    for name in ("openai", "anthropic", "google"):
        if get_api_key(name):
            model = {"openai": "gpt-4o-mini", "anthropic": "claude-haiku-4.5", "google": "gemini-2.5-flash"}[name]
            return name, model, ""

    raise typer.Exit(code=1)


def get_staged_stats(project_path: Path) -> dict[str, int]:
    lines = status_porcelain(project_path)
    modified = added = deleted = 0
    for line in lines:
        if len(line) < 2:
            continue
        x = line[0]
        if x in ("M", "R"):
            modified += 1
        elif x in ("A", "C"):
            added += 1
        elif x == "D":
            deleted += 1
    return {"modified": modified, "added": added, "deleted": deleted}


def sanitize_commit_message(commit_message: str) -> str:
    """Strip internal optimization terms from the commit message."""
    terms = ["ponytail", "yagni", "caveman", "graphify", "safe\\s+because", "prompt optimization", "reasoning"]
    pattern = re.compile(r"(?i)\b(" + "|".join(terms) + r")\b")
    lines = commit_message.splitlines()
    cleaned = []
    for line in lines:
        if pattern.search(line):
            stripped = line.strip()
            if any(stripped.startswith(c) for c in ("-", "*", "\u2022")):
                continue
            line = pattern.sub("", line)
            line = re.sub(r"\s+", " ", line).strip()
            if line:
                cleaned.append(line)
        else:
            cleaned.append(line)
    return "\n".join(cleaned).strip()


@app.callback(invoke_without_command=True)
def commit_cmd(
    ctx: typer.Context,
    path: str = typer.Option(".", "--path", "-p", help="Project root to run commit in."),
) -> None:
    """Generate a semantic commit message and create the commit."""
    if ctx.invoked_subcommand is not None:
        return
    asyncio.run(_run_commit(Path(path)))


async def _run_commit(project_path: Path) -> None:
    console = get_console()

    if not is_git_repo(project_path):
        console.print(f"[bold red]Error:[/bold red] {project_path} is not inside a git working tree.")
        raise typer.Exit(code=1)

    diff = diff_staged(project_path)
    if not diff.strip():
        console.print("No staged changes found.\nRun:\n  git add <files>\nbefore using forge commit.")
        raise typer.Exit(code=1)

    provider_name, model, api_key_env = _resolve_provider_for_commit()
    api_key = os.environ.get(api_key_env)
    if not api_key:
        from forgecli.core.credentials import get_api_key
        api_key = get_api_key(provider_name)
    if not api_key:
        console.print("[red]No API key found. Run `forge auth login` first.[/red]")
        raise typer.Exit(code=1)

    system_prompt = _COMMIT_SYSTEM_PROMPT
    prompt = (
        f"Git Diff:\n{diff}"
    )

    with console.status("[bold yellow]Thinking...[/bold yellow]", spinner="dots"):
        provider = _build_provider(provider_name, api_key)
        request = ChatRequest(
            model=model,
            messages=[
                ChatMessage(role=Role.SYSTEM, content=system_prompt),
                ChatMessage(role=Role.USER, content=prompt),
            ],
        )

        response = await provider.chat(request)
        commit_message = response.message.content.strip()

    if commit_message.startswith("```"):
        lines = commit_message.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        commit_message = "\n".join(lines).strip()

    commit_message = sanitize_commit_message(commit_message)

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
    stats_str = " \u2022 ".join(parts) if parts else "0 modified \u2022 0 added \u2022 0 deleted"

    preview_text = Text()
    preview_text.append("Repository  ", style="bold cyan")
    preview_text.append(f"{repo_name}\n", style="white")
    preview_text.append("Branch      ", style="bold cyan")
    preview_text.append(f"{branch_name}\n", style="white")
    preview_text.append("Files       ", style="bold cyan")
    preview_text.append(f"{stats_str}\n\n", style="white")
    preview_text.append("\u2500" * 40 + "\n\n", style="dim")
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
    summary_text.append("  - [bold green]\u2713 Commit Created[/bold green]\n")
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


def _build_provider(provider_name: str, api_key: str):
    """Build a provider instance directly — no DI, no registry, no bootstrap."""
    if provider_name == "openai":
        from forgecli.providers.openai import OpenAIProvider
        return OpenAIProvider(api_key=api_key)
    elif provider_name == "anthropic":
        from forgecli.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=api_key)
    elif provider_name == "google":
        from forgecli.providers.google import GeminiProvider
        return GeminiProvider(api_key=api_key)
    else:
        raise RuntimeError(f"Unknown provider: {provider_name}")


def _run_git(args: list[str], project: Path) -> str:
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
