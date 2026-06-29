"""``forgecli history`` subcommand."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import table
from forgecli.memory.history import HistoryRepository
from forgecli.memory.store import MemoryStore

app = typer.Typer(help="Inspect local CLI history.", no_args_is_help=True)


@app.command("list")
def list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum entries to show."),
) -> None:
    """Show the most recent history entries (placeholder)."""
    context = bootstrap_context()
    store: MemoryStore = context.container.resolve(MemoryStore)
    with store:
        history = HistoryRepository(store)
        entries = history.list_recent(limit=limit)
    rows: list[list[str]] = [
        [
            str(entry.id),
            entry.timestamp.isoformat(timespec="seconds"),
            entry.command,
            entry.provider or "-",
            entry.model or "-",
            str(entry.prompt_tokens),
            str(entry.completion_tokens),
        ]
        for entry in entries
    ]
    table(
        ["ID", "When", "Command", "Provider", "Model", "Prompt T", "Comp T"],
        rows,
        title="Recent history",
    )


__all__ = ["app"]
