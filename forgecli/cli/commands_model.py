"""``forge model`` subcommand group: choose an AI provider/model.

The selected choice is persisted to ``data_dir/router.json`` and read
back on every subsequent CLI invocation. ``auto`` defers to the
cheapest-compatible provider with credentials available.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console, success, table, warn
from forgecli.providers.base import ProviderRegistry
from forgecli.providers.router import (
    ModelRouter,
    SelectionMode,
)
from forgecli.providers.router_state import (
    RouterState,
    load_state,
    save_state,
)

app = typer.Typer(
    help="Choose the AI provider/model for this project (claude, openai, gemini, auto).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


_STATE_FILE = "router.json"


def _state_path(paths) -> Path:
    return paths.data_dir / _STATE_FILE


def _load(paths) -> RouterState:
    return load_state(_state_path(paths))


def _save(paths, state: RouterState) -> None:
    save_state(_state_path(paths), state)


def _build_router(context) -> ModelRouter:
    registry = context.container.resolve(ProviderRegistry)
    return ModelRouter(registry=registry)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("claude")
def claude_cmd(
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the Anthropic model (e.g. claude-3-5-sonnet-latest)."
    ),
) -> None:
    """Use Anthropic Claude as the active provider."""
    _select("claude", model_override=model, provider_override="anthropic")


@app.command("openai")
def openai_cmd(
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the OpenAI model (e.g. gpt-4o-mini)."
    ),
) -> None:
    """Use OpenAI as the active provider."""
    _select("openai", model_override=model, provider_override="openai")


@app.command("gemini")
def gemini_cmd(
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override the Google model (e.g. gemini-1.5-flash)."
    ),
) -> None:
    """Use Google Gemini as the active provider."""
    _select("gemini", model_override=model, provider_override="google")


@app.command("auto")
def auto_cmd() -> None:
    """Auto-select the cheapest compatible provider with credentials available."""
    _select("auto", model_override=None, provider_override=None)


@app.command("status")
def status_cmd() -> None:
    """Show the currently active selection and what it would route to."""
    context = bootstrap_context()
    state = _load(context.paths)
    router = _build_router(context)
    decision = router.select(state.choice)
    if state.model:
        decision = _apply_model_override(decision, state.model)
    creds = _env_summary()
    rows = [
        ["choice", state.choice],
        ["model", decision.model],
        ["provider", decision.provider_name],
        ["mode", decision.mode.value],
        ["cost in / out (per 1k tokens)", f"${decision.cost_in:.5f} / ${decision.cost_out:.5f}"],
        ["state file", str(_state_path(context.paths))],
    ]
    table(["Field", "Value"], rows, title="Model router")
    get_console().print()
    table(
        ["Provider", "API key env", "Available"],
        creds,
        title="Credentials detected",
    )


@app.command("list")
def list_cmd() -> None:
    """List every registered provider and its default model."""
    context = bootstrap_context()
    router = _build_router(context)
    rows = []
    for name in router.available_providers():
        rows.append(
            [
                name,
                router.default_model_for(name),
                "yes" if _provider_has_credentials(name) else "no",
            ]
        )
    table(["Provider", "Default model", "Credentials"], rows, title="Registered providers")


@app.command("preview")
def preview_cmd() -> None:
    """Print the routing decision the current selection would make."""
    context = bootstrap_context()
    state = _load(context.paths)
    router = _build_router(context)
    decision = router.select(state.choice)
    if state.model:
        decision = _apply_model_override(decision, state.model)
    get_console().print(decision)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _select(choice: str, *, model_override: str | None, provider_override: str | None) -> None:
    context = bootstrap_context()
    state = _load(context.paths)
    state.choice = choice
    if model_override:
        state.model = model_override
    if provider_override:
        state.provider = provider_override
    _save(context.paths, state)
    context.extras.update(state.to_extras())

    router = _build_router(context)
    decision = router.select(choice)
    if state.model:
        decision = _apply_model_override(decision, state.model)
    lines = [
        f"Active: [accent]{decision.provider_name}[/accent] / [bold]{decision.model}[/bold]",
        f"Mode:   {decision.mode.value}",
    ]
    if decision.mode is SelectionMode.FALLBACK:
        warn(
            "No provider had credentials available; the router fell back to the mock provider."
        )
    else:
        success(
            f"Switched to {decision.provider_name} ({decision.model}) — "
            f"${decision.cost_in:.5f}/1k in, ${decision.cost_out:.5f}/1k out."
        )
    for line in lines:
        get_console().print(line)


def _apply_model_override(decision, model: str):  # type: ignore[no-untyped-def]
    from forgecli.providers.router import RouteDecision, SelectionMode

    return RouteDecision(
        provider_name=decision.provider_name,
        model=model,
        mode=SelectionMode.EXPLICIT,
        cost_in=decision.cost_in,
        cost_out=decision.cost_out,
        candidates=decision.candidates,
    )


def _provider_has_credentials(name: str) -> bool:
    env_vars = {
        "openai": ("OPENAI_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "mock": (),
    }.get(name, ())
    if name == "mock":
        return True
    return any(os.environ.get(v) for v in env_vars)


def _env_summary() -> list[list[str]]:
    rows: list[list[str]] = []
    for provider, env_vars in {
        "openai": ("OPENAI_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    }.items():
        present = [v for v in env_vars if os.environ.get(v)]
        rows.append(
            [provider, ", ".join(env_vars), "yes" if present else "no"]
        )
    return rows


__all__ = ["app"]
