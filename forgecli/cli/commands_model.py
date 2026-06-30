"""``forge model`` subcommand group: choose and manage AI models."""

from __future__ import annotations

import asyncio

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console
from forgecli.providers.base import ProviderRegistry

app = typer.Typer(
    help="Manage AI models and aliases.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

MODEL_DISPLAY_NAMES = {
    # OpenAI
    "gpt-5": "GPT-5",
    "gpt-5-mini": "GPT-5 Mini",
    "gpt-4.1": "GPT-4.1",
    "gpt-4.1-mini": "GPT-4.1 Mini",
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o Mini",
    "gpt-4-turbo": "GPT-4 Turbo",
    "o1-preview": "o1 Preview",
    "o1-mini": "o1 Mini",
    # Anthropic
    "claude-opus-4.1": "Claude Opus 4.1",
    "claude-sonnet-4.5": "Claude Sonnet 4.5",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "claude-3-5-sonnet-latest": "Claude 3.5 Sonnet",
    "claude-3-5-haiku-latest": "Claude 3.5 Haiku",
    "claude-3-opus-latest": "Claude 3 Opus",
    # Google
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "gemini-1.5-pro": "Gemini 1.5 Pro",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
    "gemini-2.0-flash-exp": "Gemini 2.0 Flash Exp",
    # OpenRouter
    "glm-5.2": "GLM 5.2",
    "deepseek-v3": "DeepSeek V3",
    "deepseek-r1": "DeepSeek R1",
    "qwen3-coder": "Qwen3 Coder",
    "qwen3-32b": "Qwen3 32B",
    "kimi-k2": "Kimi K2",
    "llama-4-maverick": "Llama 4 Maverick",
    "llama-3.3-70b": "Llama 3.3 70B",
    "gemma-3": "Gemma 3",
    "devstral": "Devstral",
    "codestral": "Codestral",
    # Groq
    "llama-4-scout": "Llama 4 Scout",
    # Mistral
    "mistral-large": "Mistral Large",
    "magistral": "Magistral",
    "mistral-small": "Mistral Small",
    # Local
    "llama3": "Llama 3",
    "local-model": "Local Model",
}

STATIC_GROUPS = {
    "OpenAI": [
        "gpt-5",
        "gpt-5-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1-preview",
        "o1-mini",
    ],
    "Anthropic": [
        "claude-opus-4.1",
        "claude-sonnet-4.5",
        "claude-haiku-4.5",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-3-opus-latest",
    ],
    "Google": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-2.0-flash-exp",
    ],
    "OpenRouter": [
        "glm-5.2",
        "deepseek-v3",
        "deepseek-r1",
        "qwen3-coder",
        "qwen3-32b",
        "kimi-k2",
        "llama-4-maverick",
        "llama-3.3-70b",
        "gemma-3",
        "devstral",
        "codestral",
    ],
    "Groq": ["llama-4-scout", "deepseek-r1", "qwen3-32b"],
    "Mistral": ["mistral-large", "magistral", "mistral-small"],
}


@app.command("list")
def list_cmd() -> None:
    """List every registered provider and its supported models."""
    console = get_console()

    # Print static groups
    for group_name, models in STATIC_GROUPS.items():
        console.print(f"\n[bold]{group_name}[/bold]")
        console.print("-" * 40)
        for m in models:
            disp = MODEL_DISPLAY_NAMES.get(m, m)
            console.print(f"  {disp}")

    # Query local/dynamic models
    console.print("\n[bold]Local Providers[/bold]")
    console.print("-" * 40)

    from forgecli.providers.openai_compatible import (
        LMStudioProvider,
        OllamaProvider,
        VllmProvider,
    )

    locals_map = {
        "Ollama": (OllamaProvider, "ollama"),
        "LM Studio": (LMStudioProvider, "lmstudio"),
        "vLLM": (VllmProvider, "vllm"),
    }

    for name, (cls, _) in locals_map.items():
        console.print(f"\n  [bold]{name}[/bold]")
        try:
            p_inst = cls()
            dynamic_models = asyncio.run(p_inst.list_models())
            if dynamic_models:
                for dm in dynamic_models:
                    console.print(f"    {dm.id}")
            else:
                for sm in p_inst._known_models():
                    console.print(f"    {sm.id}")
        except Exception:
            p_inst = cls()
            for sm in p_inst._known_models():
                console.print(f"    {sm.id}")


@app.command("use")
def use(
    model: str = typer.Argument(..., help="The model ID or alias to set as default.")
) -> None:
    """Set the default model and automatically update its provider."""
    console = get_console()
    model_lower = model.lower().strip()

    found_provider = None
    display_model = MODEL_DISPLAY_NAMES.get(model_lower, model)

    for provider, models in STATIC_GROUPS.items():
        if model_lower in models or any(m.lower() == model_lower for m in models):
            found_provider = provider.lower()
            for m in models:
                if m.lower() == model_lower:
                    model_lower = m
                    display_model = MODEL_DISPLAY_NAMES.get(m, m)
                    break
            break

    if not found_provider:
        if model_lower == "llama3":
            found_provider = "ollama"
        elif model_lower == "local-model":
            found_provider = "lmstudio"
        else:
            from forgecli.config.loader import ConfigLoader

            try:
                settings = ConfigLoader().load()
                found_provider = settings.providers.default
            except Exception:
                found_provider = "mock"

    from forgecli.config.writer import update_config

    update_config(default_provider=found_provider, default_model=model_lower)
    console.print(f"[bold green]✓[/bold green] Default model changed to [bold]{display_model}[/bold]")


@app.command("current")
def current() -> None:
    """Print the currently active model."""
    console = get_console()
    from forgecli.config.loader import ConfigLoader
    from forgecli.providers.router import ModelRouter

    context = bootstrap_context()

    try:
        settings = ConfigLoader().load()
        default_p = settings.providers.default
        default_m = settings.providers.default_model
    except Exception:
        default_p = "mock"
        default_m = "auto"

    router = ModelRouter(registry=context.container.resolve(ProviderRegistry))
    if not default_m or default_m == "auto":
        default_m = router.default_model_for(default_p)

    display_model = MODEL_DISPLAY_NAMES.get(default_m.lower(), default_m)
    console.print(f"Current Model: [bold cyan]{display_model}[/bold cyan] ({default_p.capitalize()})")


@app.command("search")
def search(
    keyword: str = typer.Argument(..., help="Keyword to search models by.")
) -> None:
    """Search for models matching a keyword."""
    console = get_console()
    keyword = keyword.lower().strip()

    console.print(f"[bold]Search results for '{keyword}':[/bold]\n")
    matches = 0

    for provider, models in STATIC_GROUPS.items():
        for m in models:
            display_name = MODEL_DISPLAY_NAMES.get(m, m)
            if keyword in m.lower() or keyword in display_name.lower():
                console.print(
                    f"  • [cyan]{display_name}[/cyan] ({m}) - Provider: [bold]{provider}[/bold]"
                )
                matches += 1

    if matches == 0:
        console.print("No matching models found.")


# ---------------------------------------------------------------------------
# Backward Compatibility hidden commands
# ---------------------------------------------------------------------------


@app.command("claude", hidden=True)
def claude_cmd(
    model: str | None = typer.Option(None, "--model", "-m")
) -> None:
    from forgecli.config.writer import update_config

    update_config(default_provider="anthropic", default_model=model or "auto")
    get_console().print("[green]✓ Switched default provider to Anthropic[/green]")


@app.command("openai", hidden=True)
def openai_cmd(
    model: str | None = typer.Option(None, "--model", "-m")
) -> None:
    from forgecli.config.writer import update_config

    update_config(default_provider="openai", default_model=model or "auto")
    get_console().print("[green]✓ Switched default provider to OpenAI[/green]")


@app.command("gemini", hidden=True)
def gemini_cmd(
    model: str | None = typer.Option(None, "--model", "-m")
) -> None:
    from forgecli.config.writer import update_config

    update_config(default_provider="google", default_model=model or "auto")
    get_console().print("[green]✓ Switched default provider to Google[/green]")


@app.command("auto", hidden=True)
def auto_cmd() -> None:
    from forgecli.config.writer import update_config

    update_config(default_provider="mock", default_model="auto")
    get_console().print("[green]✓ Set to auto (mock fallback)[/green]")


@app.command("status", hidden=True)
def status_cmd() -> None:
    current()


__all__ = ["app"]
