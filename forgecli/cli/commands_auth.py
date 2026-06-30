"""``forge auth`` subcommand group."""

from __future__ import annotations

import asyncio

import typer

from forgecli.cli.ui import get_console

app = typer.Typer(
    help="Manage AI provider authentication and credentials.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.command("login")
def login(
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Provider to login to (e.g. openai, anthropic)."
    ),
    key: str | None = typer.Option(None, "--key", "-k", help="API key to use."),
) -> None:
    """Authenticate with an AI provider (launches interactive wizard)."""
    console = get_console()

    providers_list = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google Gemini"),
        ("openrouter", "OpenRouter"),
        ("groq", "Groq"),
        ("mistral", "Mistral"),
        ("ollama", "Ollama (Local)"),
        ("lmstudio", "LM Studio (Local)"),
        ("vllm", "vLLM (Local)"),
    ]

    # Step 1: Select Provider
    if not provider:
        console.print("[bold cyan]Step 1 — Select Provider[/bold cyan]")
        for idx, (_, p_display) in enumerate(providers_list, 1):
            console.print(f"  [bold green]{idx}[/bold green]. {p_display}")
        console.print()

        while True:
            selection = typer.prompt("Select a provider (1-9)")
            try:
                sel_idx = int(selection) - 1
                if 0 <= sel_idx < len(providers_list):
                    provider = providers_list[sel_idx][0]
                    break
            except ValueError:
                pass
            # Also allow typing provider name directly
            matched = [p[0] for p in providers_list if p[0] == selection.lower().strip()]
            if matched:
                provider = matched[0]
                break
            console.print("[red]Invalid selection. Please choose a number from 1 to 9.[/red]")
    else:
        provider = provider.lower().strip()
        matched = [p[0] for p in providers_list if p[0] == provider]
        if not matched:
            console.print(f"[red]Unknown provider: {provider}[/red]")
            raise typer.Exit(1)

    # Step 2: Enter API Key
    if not key:
        console.print(f"\n[bold cyan]Step 2 — Enter API Key for {provider.capitalize()}[/bold cyan]")
        while True:
            key = typer.prompt("API Key", hide_input=True)
            if not key.strip():
                console.print("[red]API Key cannot be empty.[/red]")
                continue

            # Validate common formats
            warning = None
            if provider == "openai" and not key.startswith("sk-"):
                warning = "Warning: OpenAI keys typically start with 'sk-'"
            elif provider == "anthropic" and not key.startswith("sk-ant-"):
                warning = "Warning: Anthropic keys typically start with 'sk-ant-'"
            elif provider == "google" and not key.startswith("AIza"):
                warning = "Warning: Google Gemini keys typically start with 'AIza'"
            elif provider == "openrouter" and not key.startswith("sk-or-v1-"):
                warning = "Warning: OpenRouter keys typically start with 'sk-or-v1-'"
            elif provider == "groq" and not key.startswith("gsk_"):
                warning = "Warning: Groq keys typically start with 'gsk_'"

            if warning:
                console.print(f"[yellow]{warning}[/yellow]")
                confirm = typer.confirm("Do you want to use this key anyway?")
                if not confirm:
                    continue
            break

    # Step 3: Verify
    console.print(f"\n[bold cyan]Step 3 — Verify Connection to {provider.capitalize()}[/bold cyan]")

    from forgecli.config.writer import update_config
    from forgecli.core.credentials import set_api_key
    from forgecli.core.verification import verify_provider_key

    with console.status(f"[bold green]Verifying API key with {provider.capitalize()}...[/bold green]"):
        success_verify = asyncio.run(verify_provider_key(provider, key))

    if success_verify:
        is_keyring = set_api_key(provider, key)
        storage_type = "OS keychain" if is_keyring else "encrypted credentials file"

        # Save provider as default in forgecli.toml
        update_config(default_provider=provider)

        console.print("\n[bold green]✓ Connection successful[/bold green]")
        console.print(f"[bold green]✓ API key saved securely[/bold green] ({storage_type})")
        console.print(f"[bold green]✓ Default provider:[/bold green] {provider.capitalize()}")
    else:
        console.print("\n[bold red]✗ Connection failed[/bold red]")
        console.print("[red]Verification failed. Please check your API key and network connection.[/red]")
        retry = typer.confirm("Would you like to try again?")
        if retry:
            return login(provider=provider, key=None)
        raise typer.Exit(1)


@app.command("list")
def list_cmd() -> None:
    """List all authenticated providers."""
    console = get_console()
    from forgecli.core.credentials import list_authenticated_providers

    auth_list = list_authenticated_providers()
    if not auth_list:
        console.print("No authenticated providers found. Run [bold]forge auth login[/bold] to get started.")
    else:
        console.print("[bold]Authenticated Providers:[/bold]")
        for p in auth_list:
            console.print(f"  ✓ {p.capitalize()}")


@app.command("status")
def status_cmd() -> None:
    """Show authentication status for all providers."""
    console = get_console()
    from forgecli.config.loader import ConfigLoader
    from forgecli.core.credentials import list_authenticated_providers

    try:
        settings = ConfigLoader().load()
        default_p = settings.providers.default
        default_m = settings.providers.default_model
    except Exception:
        default_p = "mock"
        default_m = "auto"

    auth_list = list_authenticated_providers()

    console.print("[bold]ForgeCLI Authentication Status[/bold]")
    console.print(f"Default Provider: [bold cyan]{default_p}[/bold cyan]")
    console.print(f"Default Model:    [bold cyan]{default_m}[/bold cyan]")
    console.print("\n[bold]Authenticated Credentials:[/bold]")
    for p in ["openai", "anthropic", "google", "openrouter", "groq", "mistral", "ollama", "lmstudio", "vllm"]:
        status = "✓ Authenticated" if p in auth_list else "✗ Unauthenticated"
        color = "green" if p in auth_list else "red"
        console.print(f"  [{color}]{status:<15}[/{color}] {p.capitalize()}")


@app.command("remove")
def remove(
    provider: str = typer.Argument(..., help="The provider to remove authentication for.")
) -> None:
    """Remove stored credentials for a provider."""
    console = get_console()
    from forgecli.core.credentials import delete_api_key

    delete_api_key(provider)
    console.print(f"✓ Removed credentials for {provider.capitalize()}")


@app.command("logout")
def logout() -> None:
    """Remove all securely stored credentials and log out."""
    console = get_console()
    from forgecli.core.credentials import delete_all_api_keys

    delete_all_api_keys()
    console.print("✓ Logged out. All stored API keys have been removed securely.")


@app.command("verify")
def verify() -> None:
    """Verify connectivity for all authenticated providers."""
    console = get_console()
    from forgecli.core.credentials import get_api_key, list_authenticated_providers
    from forgecli.core.verification import verify_provider_key

    auth_list = list_authenticated_providers()
    if not auth_list:
        console.print("No authenticated providers found.")
        return

    console.print("[bold]Verifying Authenticated Providers...[/bold]")
    for p in auth_list:
        key = get_api_key(p)
        if not key:
            continue
        with console.status(f"Verifying {p.capitalize()}..."):
            ok = asyncio.run(verify_provider_key(p, key))
        status = "[bold green]✓ Valid[/bold green]" if ok else "[bold red]✗ Verification Failed[/bold red]"
        console.print(f"  {p.capitalize():<15} {status}")


__all__ = ["app"]
