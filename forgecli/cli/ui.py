"""Rich-based terminal UI helpers."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

_THEME = Theme(
    {
        "info": "cyan",
        "warn": "yellow",
        "error": "bold red",
        "success": "bold green",
        "muted": "dim",
        "accent": "magenta",
        "accent.bold": "bold magenta",
    }
)


def get_console() -> Console:
    """Return a shared Rich :class:`Console` with the ForgeCLI theme."""
    return Console(theme=_THEME, soft_wrap=False)


def info(message: str) -> None:
    get_console().print(f"[info]ℹ[/info] {message}")


def warn(message: str) -> None:
    get_console().print(f"[warn]![/warn] {message}")


def error(message: str) -> None:
    get_console().print(f"[error]✗[/error] {message}")


def success(message: str) -> None:
    get_console().print(f"[success]✓[/success] {message}")


def table(headers: list[str], rows: list[list[str]], *, title: str | None = None) -> None:
    """Print a small :class:`rich.table.Table` to the shared console."""
    tbl = Table(title=title, header_style="accent.bold")
    for header in headers:
        tbl.add_column(header)
    for row in rows:
        tbl.add_row(*row)
    get_console().print(tbl)
