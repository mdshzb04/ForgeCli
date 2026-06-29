"""Typed exception hierarchy for ForgeCLI."""

from __future__ import annotations


class ForgeCLIError(Exception):
    """Base class for all ForgeCLI-specific errors."""


class ConfigError(ForgeCLIError):
    """Raised when configuration cannot be loaded or validated."""


class ProviderError(ForgeCLIError):
    """Raised on AI provider failures (network, auth, schema)."""


class GitError(ForgeCLIError):
    """Raised on Git-related failures (missing repo, bad ref, etc)."""


class PluginError(ForgeCLIError):
    """Raised on plugin discovery or lifecycle failures."""


class PipelineError(ForgeCLIError):
    """Raised when a builder/review/planner pipeline cannot complete."""
