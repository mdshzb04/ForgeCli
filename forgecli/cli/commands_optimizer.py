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


@app.command("explain")
def explain_opt_cmd() -> None:
    """Explain how the Ponytail prompt optimizer works and the rules it applies."""
    console = get_console()
    console.print("[bold cyan]Ponytail Prompt Optimizer[/bold cyan]")
    console.print(
        "Ponytail optimizes LLM requests by enforcing a set of rules (the Ponytail ladder) "
        "directly in the system prompt. This guides the model to produce minimal, high-quality diffs "
        "and avoid speculative implementation."
    )
    console.print("\n[bold]Key Optimization Principles:[/bold]")
    console.print("  1. [bold]YAGNI (You Aren't Gonna Need It)[/bold]: Skip speculative work/features.")
    console.print("  2. [bold]Reuse[/bold]: Prefer existing helpers and patterns in the codebase.")
    console.print("  3. [bold]Standard Library[/bold]: Prioritize Python standard library over external deps.")
    console.print("  4. [bold]Native Platform[/bold]: Native platform features beat third-party libraries.")
    console.print("  5. [bold]Installed Deps[/bold]: Use already-installed dependencies before adding new ones.")
    console.print("  6. [bold]Conciseness[/bold]: One line beats many; write the minimum code that works.")


@app.command("preview")
def preview_cmd(
    text: str = typer.Argument(..., help="Sample user prompt to preview."),
) -> None:
    """Show a preview of the prompt optimization."""
    context = bootstrap_context()
    state = _load_persisted(_state_path(context.paths))
    ruleset = PonytailRulesetOptimizer(intensity=state.intensity)
    request = ChatRequest(
        model="preview",
        messages=[ChatMessage(role=Role.USER, content=text)],
    )
    result = asyncio.run(ruleset.optimize_chat(request))
    system_msg = next(
        (m.content for m in result.request.messages if m.role is Role.SYSTEM), ""
    )
    
    strategy = _resolve_ruleset_label(state)
    token_red = "0%" if state.intensity is Intensity.OFF else "15-30% (fewer lines of code)"
    context_savings = "0 tokens" if state.intensity is Intensity.OFF else "120-250 tokens per exchange"

    console = get_console()
    console.print("[bold cyan]Ponytail Prompt Optimization Preview[/bold cyan]")
    console.print(f"• [bold]Original Prompt:[/bold]\n  {text}")
    console.print(f"• [bold]Optimized Prompt:[/bold]\n  {system_msg or '(none)'}")
    console.print(f"• [bold]Optimization Strategy:[/bold] {strategy}")
    console.print(f"• [bold]Estimated Token Reduction:[/bold] {token_red}")
    console.print(f"• [bold]Estimated Context Savings:[/bold] {context_savings}")


__all__ = ["app"]

