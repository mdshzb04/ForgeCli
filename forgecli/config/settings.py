"""Pydantic models describing the typed ForgeCLI configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSection(BaseModel):
    """Top-level application metadata."""

    model_config = ConfigDict(extra="allow")

    name: str = "forgecli"
    version: str = "0.1.0"
    log_level: str = "INFO"
    data_dir: Path = Field(default_factory=lambda: Path("~/.local/share/forgecli"))
    plugins_dir: Path = Field(default_factory=lambda: Path("~/.config/forgecli/plugins"))


class ProviderSection(BaseModel):
    """Configuration for a single AI provider."""

    model_config = ConfigDict(extra="allow")

    api_key_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    default_model: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.2
    enabled: bool = True


class ProvidersConfig(BaseModel):
    """Provider registry configuration."""

    model_config = ConfigDict(extra="allow")

    default: str = "mock"
    default_model: str = "auto"
    allowed: list[str] = Field(default_factory=lambda: ["mock"])
    providers: dict[str, ProviderSection] = Field(default_factory=dict)


class GitSection(BaseModel):
    """Git automation settings."""

    model_config = ConfigDict(extra="allow")

    default_branch: str = "main"
    user_name: str = ""
    user_email: str = ""
    auto_fetch: bool = True
    push_on_commit: bool = False
    sign_commits: bool = False


class OptimizerSection(BaseModel):
    """Context optimizer settings."""

    model_config = ConfigDict(extra="allow")

    max_context_tokens: int = 200_000
    chunk_size: int = 4000
    chunk_overlap: int = 200
    strategy: str = "auto"  # auto | sliding | map-reduce | graph


class PromptOptimizerSection(BaseModel):
    """Ponytail prompt-optimizer settings."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    intensity: str = "lite"  # off | lite | full | ultra
    backend: str = "ruleset"  # ruleset | cli | auto
    binary: str = "ponytail"  # only used when backend = "cli"
    timeout_seconds: float = 30.0


class GraphSection(BaseModel):
    """Repository graph settings."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    languages: list[str] = Field(default_factory=lambda: ["python", "typescript"])
    max_depth: int = 8
    ignore_patterns: list[str] = Field(default_factory=list)


class MemorySection(BaseModel):
    """Local memory store settings."""

    model_config = ConfigDict(extra="allow")

    db_path: Path = Field(default_factory=lambda: Path("~/.local/share/forgecli/history.db"))
    history_limit: int = 1000
    embedding_provider: str = "mock"


class ReviewSection(BaseModel):
    """Code review settings."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    auto_review: bool = False
    max_diff_lines: int = 2000
    lint_first: bool = True


class BuilderSection(BaseModel):
    """Builder/pipeline settings."""

    model_config = ConfigDict(extra="allow")

    auto_format: bool = True
    formatter: str = "auto"
    test_command: str = ""
    max_iterations: int = 3


class PlannerSection(BaseModel):
    """Planner/agent settings."""

    model_config = ConfigDict(extra="allow")

    default_strategy: str = "react"
    max_steps: int = 20
    allow_shell: bool = False


class PromptsSection(BaseModel):
    """Prompt template settings."""

    model_config = ConfigDict(extra="allow")

    dir: Path = Field(default_factory=lambda: Path("~/.config/forgecli/prompts"))
    render_backend: str = "jinja"


class TelemetrySection(BaseModel):
    """Telemetry and analytics settings."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    endpoint: str = ""


class ForgeSettings(BaseSettings):
    """Root settings model combining file config and environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="FORGECLI_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    app: AppSection = Field(default_factory=AppSection)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    git: GitSection = Field(default_factory=GitSection)
    optimizer: OptimizerSection = Field(default_factory=OptimizerSection)
    prompt_optimizer: PromptOptimizerSection = Field(default_factory=PromptOptimizerSection)
    graph: GraphSection = Field(default_factory=GraphSection)
    memory: MemorySection = Field(default_factory=MemorySection)
    review: ReviewSection = Field(default_factory=ReviewSection)
    builder: BuilderSection = Field(default_factory=BuilderSection)
    planner: PlannerSection = Field(default_factory=PlannerSection)
    prompts: PromptsSection = Field(default_factory=PromptsSection)
    telemetry: TelemetrySection = Field(default_factory=TelemetrySection)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "app",
        "providers",
        "git",
        "optimizer",
        "prompt_optimizer",
        "graph",
        mode="before",
    )
    @classmethod
    def _coerce_none(cls, value: Any) -> Any:
        """Allow empty sections to be passed as ``None``."""
        return value or {}
