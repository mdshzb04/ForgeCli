"""Build the :class:`AppContext` for a CLI invocation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forgecli.config.loader import ConfigLoader
from forgecli.core.context import AppContext
from forgecli.core.logging import configure_logging, get_logger
from forgecli.optimizer.ponytail.state import OptimizerState
from forgecli.providers.anthropic import AnthropicProvider
from forgecli.providers.base import ProviderRegistry, default_registry
from forgecli.providers.google import GeminiProvider
from forgecli.providers.mock import MockProvider
from forgecli.providers.openai import OpenAIProvider
from forgecli.providers.router_state import load_state as load_router_state
from forgecli.utils.paths import ProjectPaths

if TYPE_CHECKING:  # pragma: no cover - typing only
    from forgecli.core.container import Container
    from forgecli.optimizer.summarizer import Summarizer

log = get_logger(__name__)


def bootstrap_context(
    *,
    config_path: Path | None = None,
    cwd: Path | str | None = None,
    extras: dict[str, Any] | None = None,
) -> AppContext:
    """Build an :class:`AppContext` with default services registered."""
    if isinstance(cwd, str):
        cwd = Path(cwd)
    import click
    try:
        click_ctx = click.get_current_context(silent=True)
    except Exception:
        click_ctx = None

    if (
        click_ctx is not None
        and click_ctx.obj is not None
        and isinstance(click_ctx.obj, AppContext)
    ):
        return click_ctx.obj

    paths = ProjectPaths.from_env(cwd=cwd).ensure()

    verbose = (extras or {}).get("verbose", False)
    level = "DEBUG" if verbose else "INFO"
    configure_logging(level=level)

    loader = ConfigLoader(config_path) if config_path else ConfigLoader()

    from forgecli.providers.openai_compatible import (
        CohereProvider,
        FireworksProvider,
        GroqProvider,
        LMStudioProvider,
        MiniMaxProvider,
        MistralProvider,
        NvidiaProvider,
        OllamaProvider,
        OpenRouterProvider,
        TogetherProvider,
        VllmProvider,
        XaiProvider,
    )

    provider_registry: ProviderRegistry = default_registry
    for name, cls in (
        ("mock", MockProvider),
        ("openai", OpenAIProvider),
        ("anthropic", AnthropicProvider),
        ("google", GeminiProvider),
        ("openrouter", OpenRouterProvider),
        ("groq", GroqProvider),
        ("mistral", MistralProvider),
        ("minimax", MiniMaxProvider),
        ("xai", XaiProvider),
        ("together", TogetherProvider),
        ("fireworks", FireworksProvider),
        ("cohere", CohereProvider),
        ("nvidia", NvidiaProvider),
        ("ollama", OllamaProvider),
        ("lmstudio", LMStudioProvider),
        ("vllm", VllmProvider),
    ):
        provider_registry.register(name, cls)

    container = _build_container(provider_registry, paths)
    context = AppContext(paths=paths, loader=loader, container=container)
    merged = dict(extras or {})
    merged.setdefault(
        "optimizer.state",
        _load_optimizer_state(paths),
    )
    merged.setdefault(
        "router.state",
        load_router_state(paths.data_dir / "router.json"),
    )
    context.extras.update(merged)
    if click_ctx is not None:
        click_ctx.obj = context
    return context


def _load_optimizer_state(paths: ProjectPaths) -> OptimizerState:
    """Read the persisted optimizer state from ``data_dir/optimizer.json``."""
    state_path = paths.data_dir / "optimizer.json"
    if not state_path.exists():
        return OptimizerState()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OptimizerState()
    from forgecli.optimizer.ponytail import Intensity

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


def _build_container(
    provider_registry: ProviderRegistry,
    paths: ProjectPaths,
):
    """Register default services in the DI container."""
    from forgecli.core.container import Container
    from forgecli.graph.backend_graphify import GraphifyRepositoryGraph
    from forgecli.graph.graph import CodeGraph
    from forgecli.graph.indexer import Indexer
    from forgecli.graph.repository import RepositoryGraph
    from forgecli.memory.store import MemoryStore
    from forgecli.optimizer.chunker import Chunker
    from forgecli.optimizer.optimizer import ContextOptimizer
    from forgecli.optimizer.ponytail import PromptOptimizer
    from forgecli.optimizer.ponytail.factory import build_optimizer
    from forgecli.optimizer.ranker import Ranker
    from forgecli.optimizer.summarizer import Summarizer
    from forgecli.prompts.loader import PromptLoader
    from forgecli.prompts.registry import PromptRegistry
    from forgecli.prompts.renderer import PromptRenderer
    from forgecli.providers.router import ModelRouter
    from forgecli.templates.engine import TemplateEngine
    from forgecli.templates.registry import TemplateRegistry

    container = Container()

    container.register_instance(ProviderRegistry, provider_registry)
    container.register_instance(ProjectPaths, paths)
    container.register_instance(CodeGraph, CodeGraph())

    container.register(MemoryStore, lambda c: MemoryStore(paths.data_dir / "history.db"))
    container.register(Summarizer, lambda c: _build_default_summarizer(c))
    container.register(
        ContextOptimizer,
        lambda c: ContextOptimizer(
            chunker=Chunker(),
            ranker=Ranker(),
            summarizer=c.resolve(Summarizer) if c.has(Summarizer) else None,
        ),
    )
    container.register(
        Indexer,
        lambda c: Indexer(
            graph=c.resolve(CodeGraph),
            root=paths.cwd,
        ),
    )
    container.register(
        RepositoryGraph,  # type: ignore[type-abstract]
        lambda _c: GraphifyRepositoryGraph(root=paths.cwd),
    )
    container.register(
        PromptOptimizer,  # type: ignore[type-abstract]
        lambda _c: build_optimizer(_load_optimizer_state(paths), ConfigLoader().load()),
    )
    container.register(
        ModelRouter,
        lambda c: ModelRouter(registry=c.resolve(ProviderRegistry)),
    )
    container.register(PromptRenderer, lambda _c: PromptRenderer())
    container.register(
        PromptLoader, lambda _c: PromptLoader(paths.prompts_dir)
    )
    container.register(PromptRegistry, lambda _c: PromptRegistry())
    container.register(TemplateEngine, lambda c: TemplateEngine(renderer=c.resolve(PromptRenderer)))
    container.register(TemplateRegistry, lambda _c: TemplateRegistry())

    return container


def _build_default_summarizer(container: Container) -> Summarizer:
    """Wire the default summarizer against the mock provider.

    Real provider wiring will live in a separate composition function and
    will be selected via configuration.
    """
    from forgecli.optimizer.summarizer import Summarizer
    from forgecli.providers.mock import MockProvider, MockProviderConfig

    provider = MockProvider(MockProviderConfig())
    return Summarizer(provider=provider)


def resolve_provider_and_decision(
    *,
    live: bool,
    cwd: Path | str,
) -> tuple[Any, Any]:
    """Unified provider and route decision resolver for all AI commands.

    If live is True and no provider has credentials (which resolves to mock),
    it displays the error requesting configuration and exits with code 1.
    """
    import typer

    from forgecli.providers.base import ProviderRegistry
    from forgecli.providers.mock import MockProvider, MockProviderConfig
    from forgecli.providers.router import (
        ModelRouter,
        RouteDecision,
        SelectionMode,
        _provider_has_credentials,
    )
    from forgecli.providers.router_state import load_state as load_router_state

    if isinstance(cwd, str):
        cwd = Path(cwd)

    app_context = bootstrap_context(cwd=cwd)
    state = load_router_state(app_context.paths.data_dir / "router.json")
    router = app_context.container.resolve(ModelRouter)
    decision = router.select(state.choice)

    if not live:
        provider = MockProvider(MockProviderConfig())
        decision = RouteDecision(
            provider_name="mock",
            model=decision.model,
            mode=SelectionMode.FALLBACK,
        )
        return provider, decision

    if decision.provider_name == "mock" or not _provider_has_credentials(decision.provider_name):
        from forgecli.cli.ui import error
        error(
            "No AI provider configured.\n\n"
            "Run:\n"
            "  forge auth login\n"
            "  forge provider use <provider>\n"
            "  forge model use <model>\n\n"
            "Then retry."
        )
        raise typer.Exit(code=1)

    registry = app_context.container.resolve(ProviderRegistry)
    if not registry.has(decision.provider_name):
        from forgecli.cli.ui import error
        error(f"Unknown provider '{decision.provider_name}'.")
        raise typer.Exit(code=1)

    provider_cls = registry.get(decision.provider_name)
    provider = provider_cls()  # type: ignore[call-arg]
    return provider, decision

