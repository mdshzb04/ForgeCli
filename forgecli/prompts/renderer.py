"""Render prompt templates into strings."""

from __future__ import annotations

from forgecli.core.service import Service


class PromptRenderer(Service):
    """Render prompt templates with a small variable substitution.

    A real implementation will use Jinja2; for now we support a tiny
    ``{var}`` syntax so the rest of the system can be exercised without
    the dependency being required.
    """

    name = "prompts.renderer"

    def render(self, template: str, **variables: object) -> str:
        """Substitute ``{name}`` occurrences in ``template``."""
        result = template
        for key, value in variables.items():
            result = result.replace("{" + key + "}", str(value))
        return result
