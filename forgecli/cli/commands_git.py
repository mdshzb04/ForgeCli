"""``forgecli git`` subcommand group."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.commands_commit import _git_commit
from forgecli.cli.commands_forge import _build_provider_for
from forgecli.cli.ui import error, get_console, success, warn
from forgecli.commit.git_utils import diff_staged, is_git_repo
from forgecli.core.errors import GitError
from forgecli.optimizer.ponytail import PromptOptimizer
from forgecli.providers.base import ChatMessage, ChatRequest, Role
from forgecli.providers.router import ModelRouter
from forgecli.providers.router_state import load_state as load_router_state

app = typer.Typer(
    help="Inspect and operate on the git repository.",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context) -> None:
    """Inspect and operate on the git repository."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(status)


@app.command("status")
def status() -> None:
    """Show repository status."""
    try:
        from forgecli.git.repo import GitRepo
        repo = GitRepo(Path.cwd())
    except GitError as exc:
        raise typer.Exit(code=1) from exc
    success(f"Branch: {repo.status().get('branch', 'unknown')}")


async def _generate_ai_commit_message(project: Path) -> str:
    diff = diff_staged(project)
    if not diff.strip():
        warn("No staged changes to commit. Stage files first (git add ...).")
        raise typer.Exit(code=1)

    app_context = bootstrap_context(cwd=project)

    # 3. Use the configured provider and selected model.
    try:
        provider = _build_provider_for(live=True, cwd=project)
    except Exception as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc

    optimizer = app_context.container.resolve(PromptOptimizer)  # type: ignore[type-abstract]
    router = app_context.container.resolve(ModelRouter)  # type: ignore[type-abstract]
    state = load_router_state(app_context.paths.data_dir / "router.json")
    decision = router.select(state.choice or "auto")
    model = decision.model

    system_prompt = (
        "You are an expert developer assistant. Generate a high-quality Conventional Commit message for the following git diff.\n"
        "The message must strictly follow the Conventional Commits specification:\n"
        "<type>(<scope>): <summary>\n\n"
        "[optional body]\n\n"
        "Rules:\n"
        "- The subject line (first line) should be concise (50 characters or less if possible, maximum 72 characters) and not end with a period.\n"
        "- Use lowercase for the type and scope.\n"
        "- Use imperative mood in the summary (e.g., \"add\", \"fix\", \"refactor\", not \"added\", \"fixes\", \"refactored\").\n"
        "- The body should be separated from the subject by a blank line.\n"
        "- The body should contain bullet points starting with '• ' (not '-') describing the changes in detail.\n"
        "- Print ONLY the generated commit message, without any markdown code block formatting (no ``` or similar), no introductory or concluding text. Just the commit message."
    )

    request = ChatRequest(
        model=model,
        messages=[
            ChatMessage(role=Role.SYSTEM, content=system_prompt),
            ChatMessage(role=Role.USER, content=f"Here is the git diff:\n{diff}"),
        ]
    )

    # 2. Use Ponytail.
    optimized_request = await optimizer.optimize_chat(request)

    response = await provider.chat(optimized_request.request)
    commit_msg = response.message.content.strip()

    # Strip code block formatting if LLM returned it
    if commit_msg.startswith("```"):
        lines = commit_msg.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        commit_msg = "\n".join(lines).strip()

    return commit_msg


@app.command("message")
def git_message() -> None:
    """Generate a Conventional Commit message and print it (no commit)."""
    project = Path.cwd()
    if not is_git_repo(project):
        error(f"{project} is not inside a git working tree.")
        raise typer.Exit(code=1)

    commit_msg = asyncio.run(_generate_ai_commit_message(project))
    print(commit_msg)


@app.command("commit")
def git_commit(
    message: str | None = typer.Option(
        None, "-m", "--message", help="Override the generated message."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation and commit immediately."
    ),
) -> None:
    """Generate a semantic commit message and create the commit."""
    project = Path.cwd()
    if not is_git_repo(project):
        error(f"{project} is not inside a git working tree.")
        raise typer.Exit(code=1)

    commit_msg = message or asyncio.run(_generate_ai_commit_message(project))

    if not yes:
        console = get_console()
        console.print("──────────────────────────────────────", style="cyan")
        console.print("\n[bold cyan]AI Generated Commit[/bold cyan]\n")
        console.print(commit_msg)
        console.print("\n──────────────────────────────────────", style="cyan")
        console.print("\nPress ENTER to commit")
        console.print("Press Ctrl+C to cancel\n")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Commit cancelled.[/yellow]")
            raise typer.Exit(0) from None

    sha = _git_commit(commit_msg, project, signoff=False)
    if sha:
        success(f"Committed {sha[:8]}")


__all__ = ["app"]
