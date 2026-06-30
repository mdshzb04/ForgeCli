"""``forge optimizer`` subcommand: turn the Ponytail prompt optimizer on/off
and set the intensity (lite / full / ultra).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import error, get_console, success, table
from forgecli.optimizer.ponytail import Intensity, PonytailRulesetOptimizer
from forgecli.optimizer.ponytail.state import OptimizerState
from forgecli.providers.base import ChatMessage, ChatRequest, Role

app = typer.Typer(
    help="Control the Ponytail prompt optimizer (on/off + intensity).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


_STATE_FILE_NAME = "optimizer.json"


def _state_path(paths) -> Path:
    return paths.data_dir / _STATE_FILE_NAME


def _load_persisted(path: Path) -> OptimizerState:
    if not path.exists():
        return OptimizerState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OptimizerState()
    state = OptimizerState()
    intensity = payload.get("intensity")
    if isinstance(intensity, str):
        try:
            state.intensity = Intensity.parse(intensity)
        except ValueError:
            state.intensity = Intensity.LITE
    backend = payload.get("backend")
    if isinstance(backend, str):
        state.backend = backend
    binary = payload.get("binary")
    if isinstance(binary, str):
        state.binary = binary
    return state


def _persist(path: Path, state: OptimizerState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "intensity": state.intensity.value,
                "backend": state.backend,
                "binary": state.binary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _apply(level: Intensity) -> OptimizerState:
    context = bootstrap_context()
    state = _load_persisted(_state_path(context.paths))
    state.intensity = level
    _persist(_state_path(context.paths), state)
    context.extras.update(state.to_extras())
    return state


@app.command("on")
def on_cmd() -> None:
    """Turn the optimizer on (restores last intensity, default ``lite``)."""
    context = bootstrap_context()
    current = _load_persisted(_state_path(context.paths))
    target = (
        current.intensity
        if current.intensity is not Intensity.OFF
        else Intensity.LITE
    )
    state = _apply(target)
    success(f"Optimizer on (intensity={state.intensity.value}).")


@app.command("off")
def off_cmd() -> None:
    """Turn the optimizer off."""
    _apply(Intensity.OFF)
    success("Optimizer off. Prompts will be passed through unchanged.")


@app.command("lite")
def lite_cmd() -> None:
    """Set intensity to ``lite`` (default)."""
    _apply(Intensity.LITE)
    success("Optimizer intensity = lite.")


@app.command("full")
def full_cmd() -> None:
    """Set intensity to ``full`` (enforce the Ponytail ladder)."""
    _apply(Intensity.FULL)
    success("Optimizer intensity = full.")


@app.command("ultra")
def ultra_cmd() -> None:
    """Set intensity to ``ultra`` (YAGNI extremist)."""
    _apply(Intensity.ULTRA)
    success("Optimizer intensity = ultra.")


@app.command("status")
def status_cmd() -> None:
    """Show the current intensity, backend, and binary path."""
    context = bootstrap_context()
    state = _load_persisted(_state_path(context.paths))
    settings = context.resolve_settings()
    global_enabled = settings.prompt_optimizer.enabled
    effective_enabled = global_enabled and (state.intensity is not Intensity.OFF)
    ruleset = _resolve_ruleset_label(state)
    rows = [
        ["enabled (global config)", "Yes" if global_enabled else "No"],
        ["enabled (effective)", "Yes" if effective_enabled else "No"],
        ["intensity", state.intensity.value],
        ["backend", state.backend],
        ["binary", state.binary],
        ["state file", str(_state_path(context.paths))],
        ["ruleset in effect", ruleset],
    ]
    table(["Field", "Value"], rows, title="Ponytail prompt optimizer")


def _resolve_ruleset_label(state: OptimizerState) -> str:
    if state.intensity is Intensity.OFF:
        return "passthrough"
    if state.intensity is Intensity.LITE:
        return "lite: name the lazier alternative"
    if state.intensity is Intensity.FULL:
        return "full: ladder enforced, shortest diff"
    return "ultra: YAGNI extremist"


@app.command("set")
def set_cmd(
    intensity: str = typer.Argument(
        ...,
        help="One of: off | lite | full | ultra.",
    ),
    backend: str | None = typer.Option(
        None,
        "--backend",
        help="Backend to use: ruleset | cli | auto.",
    ),
    binary: str | None = typer.Option(
        None,
        "--binary",
        help="Override the ponytail binary path (backend=cli/auto).",
    ),
) -> None:
    """Set the intensity (and optionally the backend/binary) in one step."""
    try:
        level = Intensity.parse(intensity)
    except ValueError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc

    context = bootstrap_context()
    state = _load_persisted(_state_path(context.paths))
    state.intensity = level
    if backend is not None:
        state.backend = backend
    if binary is not None:
        state.binary = binary
    _persist(_state_path(context.paths), state)
    context.extras.update(state.to_extras())
    success(
        f"Optimizer configured: intensity={state.intensity.value} "
        f"backend={state.backend} binary={state.binary}"
    )


@app.command("preview")
def preview_cmd(
    text: str = typer.Argument(..., help="Sample user prompt to preview."),
) -> None:
    """Show what the optimizer would prepend to a system message."""
    context = bootstrap_context()
    state = _load_persisted(_state_path(context.paths))
    ruleset = PonytailRulesetOptimizer(intensity=state.intensity)
    request = ChatRequest(
        model="preview",
        messages=[ChatMessage(role=Role.USER, content=text)],
    )
    result = asyncio.run(ruleset.optimize_chat(request))
    system = next(
        (m.content for m in result.request.messages if m.role is Role.SYSTEM), ""
    )
    get_console().print(
        f"[muted]intensity={state.intensity.value} source={result.source}[/muted]\n"
        f"[muted]notes: {', '.join(result.notes) or '(none)'}[/muted]\n\n"
        f"{system or '(no system message)'}"
    )


__all__ = ["app"]

