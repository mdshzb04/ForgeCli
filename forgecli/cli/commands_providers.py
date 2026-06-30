"""``forge provider`` subcommand group."""

from __future__ import annotations

import typer

from forgecli.cli.bootstrap import bootstrap_context
from forgecli.cli.ui import get_console

app = typer.Typer(
    help="Manage AI providers and set defaults.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

PROVIDERS_DISPLAY = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "openrouter": "OpenRouter",
    "google": "Google Gemini",
    "groq": "Groq",
    "mistral": "Mistral",
    "ollama": "Ollama",
    "lmstudio": "LM Studio",
    "vllm": "vLLM",
}


@app.command("list")
def list_cmd() -> None:
    """List every supported provider and its authentication status."""
    console = get_console()
    from forgecli.config.loader import ConfigLoader
    from forgecli.core.credentials import list_authenticated_providers

    try:
        settings = ConfigLoader().load()
        default_p = settings.providers.default.lower().strip()
    except Exception:
        default_p = "mock"

    auth_list = list_authenticated_providers()

    for p_id, p_display in PROVIDERS_DISPLAY.items():
        is_auth = p_id in auth_list
        # Local providers can be active/used even without auth (e.g. no key required)
        if p_id in ("ollama", "lmstudio", "vllm"):
            # Check if active in env/default or check if authenticated
            is_auth = is_auth or (default_p == p_id)

        status_char = "✓" if is_auth else "✗"
        color = "green" if is_auth else "red"
        default_suffix = " (default)" if default_p == p_id else ""

        console.print(f"[{color}]{status_char}[/{color}] {p_display}{default_suffix}")


@app.command("use")
def use(
    provider: str = typer.Argument(..., help="The provider to use as default.")
) -> None:
    """Set the default AI provider."""
    console = get_console()
    provider_lower = provider.lower().strip()

    # Map gemini to google for consistency
    if provider_lower == "gemini":
        provider_lower = "google"

    if provider_lower not in PROVIDERS_DISPLAY and provider_lower != "mock":
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"Supported providers: {', '.join(PROVIDERS_DISPLAY.keys())}")
        raise typer.Exit(1)

    from forgecli.config.writer import update_config
    update_config(default_provider=provider_lower)

    display_name = PROVIDERS_DISPLAY.get(provider_lower, provider_lower.capitalize())
    console.print(f"[bold green]✓[/bold green] Default provider changed to [bold]{display_name}[/bold]")


@app.command("current")
def current() -> None:
    """Print the currently active provider and default model."""
    console = get_console()
    context = bootstrap_context()
    from forgecli.config.loader import ConfigLoader
    from forgecli.providers.base import ProviderRegistry
    from forgecli.providers.router import ModelRouter

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

    display_name = PROVIDERS_DISPLAY.get(default_p.lower(), default_p.capitalize())

    console.print("[bold]Current Provider[/bold]\n")
    console.print(f"[bold cyan]{display_name}[/bold cyan]")
    console.print(f"Model: {default_m}")


__all__ = ["app"]
