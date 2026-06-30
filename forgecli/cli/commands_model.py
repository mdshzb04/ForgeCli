"""``forge model`` subcommand group: choose and manage AI models."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console
from forgecli.core.credentials import list_authenticated_providers
from forgecli.core.models import MODEL_CATALOG, get_display_name, get_model_def
from forgecli.providers.base import ProviderRegistry

app = typer.Typer(
    help="Manage AI models and aliases.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Friendly mapping for printing provider names
PROVIDER_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google Gemini",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "mistral": "Mistral",
    "minimax": "MiniMax",
    "xai": "xAI (Grok)",
    "together": "Together AI",
    "fireworks": "Fireworks AI",
    "cohere": "Cohere",
    "nvidia": "NVIDIA NIM",
    "ollama": "Ollama",
    "lmstudio": "LM Studio",
    "vllm": "vLLM",
    "mock": "Mock",
}


@app.command("list")
def list_cmd() -> None:
    """List every registered provider and its supported models."""
    console = get_console()

    from forgecli.config.loader import ConfigLoader

    context = bootstrap_context()

    default_p: str | None = None
    default_m: str | None = None
    try:
        settings = ConfigLoader().load()
        default_p = settings.providers.default
        default_m = settings.providers.default_model
    except Exception:
        pass

    if default_p:
        active_p_disp = PROVIDER_DISPLAY_NAMES.get(default_p, default_p.capitalize())
    else:
        active_p_disp = "Not configured"

    active_m_disp = get_display_name(default_m) if default_m else "Not configured"

    console.print(f"[bold]Default Provider:[/bold] {active_p_disp}")
    console.print(f"[bold]Default Model:[/bold]    {active_m_disp}\n")

    auth_list = list_authenticated_providers()

    # Providers order
    providers_order = [
        "openai",
        "anthropic",
        "google",
        "openrouter",
        "groq",
        "mistral",
        "minimax",
        "xai",
        "together",
        "fireworks",
        "cohere",
        "nvidia",
        "ollama",
        "lmstudio",
        "vllm",
    ]

    for p_id in providers_order:
        p_name = PROVIDER_DISPLAY_NAMES.get(p_id, p_id.capitalize())
        is_default = (p_id == default_p)
        is_configured = (p_id in auth_list) or (p_id in ["ollama", "lmstudio", "vllm"])

        status_char = "✓" if is_configured else "✗"
        color = "green" if is_configured else "red"
        default_suffix = " (Default)" if is_default else ""

        console.print(f"[{color}]{status_char}[/{color}] [bold]{p_name}[/bold]{default_suffix}")

        p_models = [m for m in MODEL_CATALOG if m.provider == p_id]

        dynamic_models = []
        if p_id in ["ollama", "lmstudio", "vllm"]:
            try:
                import asyncio
                registry = context.container.resolve(ProviderRegistry)
                provider_cls = registry.get(p_id)
                provider_inst = provider_cls()  # type: ignore[call-arg]
                dynamic_models = asyncio.run(provider_inst.list_models())
            except Exception:
                pass

        if dynamic_models:
            for dm in dynamic_models:
                console.print(f"  {dm.name}")
        else:
            latest_group = [m for m in p_models if m.tier == "latest"]
            rec_group = [m for m in p_models if m.tier == "recommended"]
            normal_group = [m for m in p_models if m.tier == "normal"]
            legacy_group = [m for m in p_models if m.tier == "legacy"]
            deprecated_group = [m for m in p_models if m.tier == "deprecated"]

            for m in latest_group:
                console.print(f"  ★ {m.display_name}")
            for m in rec_group:
                console.print(f"  ✓ {m.display_name}")
            for m in normal_group:
                console.print(f"  {m.display_name}")

            if legacy_group:
                console.print("  Legacy")
                for m in legacy_group:
                    console.print(f"    {m.display_name}")

            if deprecated_group:
                console.print("  Deprecated")
                for m in deprecated_group:
                    console.print(f"    {m.display_name}")

        console.print("")


@app.command("use")
def use(
    model: str = typer.Argument(..., help="The model ID or alias to set as default.")
) -> None:
    """Set the default model and automatically update its provider."""
    console = get_console()
    model_lower = model.lower().strip()

    found_m = get_model_def(model_lower)
    if not found_m:
        for m in MODEL_CATALOG:
            if m.display_name.lower() == model_lower or m.id.lower() == model_lower:
                found_m = m
                break

    if found_m:
        found_provider = found_m.provider
        model_id = found_m.id
        display_model = found_m.display_name
    else:
        model_id = model_lower
        display_model = model
        from forgecli.config.loader import ConfigLoader
        try:
            settings = ConfigLoader().load()
            found_provider = settings.providers.default or "mock"
        except Exception:
            found_provider = "mock"

    from forgecli.config.writer import update_config
    update_config(default_provider=found_provider, default_model=model_id)
    console.print(f"[bold green]✓[/bold green] Default model changed to [bold]{display_model}[/bold]")


@app.command("current")
def current() -> None:
    """Print the currently active model."""
    console = get_console()
    from forgecli.config.loader import ConfigLoader
    from forgecli.providers.router import ModelRouter

    context = bootstrap_context()

    default_p: str | None = None
    default_m: str | None = None
    try:
        settings = ConfigLoader().load()
        default_p = settings.providers.default
        default_m = settings.providers.default_model
    except Exception:
        pass

    if not default_m or default_m == "auto":
        if default_p:
            router = ModelRouter(registry=context.container.resolve(ProviderRegistry))
            default_m = router.default_model_for(default_p)
        else:
            default_m = None

    if default_m:
        display_model = get_display_name(default_m)
        p_disp = PROVIDER_DISPLAY_NAMES.get(default_p, default_p.capitalize()) if default_p else "Unknown"
        console.print(f"Current Model: [bold cyan]{display_model}[/bold cyan] ({p_disp})")
    else:
        console.print("Current Model: [bold cyan]Not configured[/bold cyan]")


@app.command("search")
def search(
    keyword: str = typer.Argument(..., help="Keyword to search models by.")
) -> None:
    """Search for models matching a keyword."""
    console = get_console()
    keyword = keyword.lower().strip()

    console.print(f"[bold]Search results for '{keyword}':[/bold]\n")
    matches = 0

    for m in MODEL_CATALOG:
        if keyword in m.id.lower() or keyword in m.display_name.lower():
            p_name = PROVIDER_DISPLAY_NAMES.get(m.provider, m.provider.capitalize())
            tier_suffix = f" [{m.tier}]" if m.tier != "normal" else ""
            console.print(
                f"  • [cyan]{m.display_name}[/cyan] ({m.id}){tier_suffix} - Provider: [bold]{p_name}[/bold]"
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
