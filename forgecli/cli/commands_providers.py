"""``forgecli providers`` subcommand group."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import table
from forgecli.providers.base import ProviderRegistry

app = typer.Typer(help="Manage AI providers.", no_args_is_help=True)


@app.command("list")
def list_cmd() -> None:
    """List registered providers (placeholder)."""
    context = bootstrap_context()
    registry = context.container.resolve(ProviderRegistry)
    table(
        ["Provider"],
        [[name] for name in registry.names()],
        title="Registered providers",
    )


__all__ = ["app"]
