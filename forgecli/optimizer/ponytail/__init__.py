"""Ponytail prompt-optimizer integration.

ForgeCLI integrates the [Ponytail](https://ponytail.dev/) ruleset
behind a small :class:`PromptOptimizer` interface and applies it
transparently to every chat call. Two implementations are shipped:

* :class:`PonytailRulesetOptimizer` — a self-contained Python
  implementation of the Ponytail "ladder" (lite / full / ultra).
  Always available, no external dependencies.
* :class:`PonytailCLIOptimizer` — an optional adapter that shells out
  to an external ``ponytail`` binary if one is on ``PATH``.

The :class:`CompositeOptimizer` picks between them at runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from forgecli.providers.base import ChatMessage, ChatRequest


class Intensity(str, Enum):
    """How aggressively to optimize prompts.

    The semantics match the Ponytail commands exactly:

    * ``off``   - no rewriting; pass prompts through unchanged.
    * ``lite``  - default; appends a one-line hint naming the lazier
                  alternative and lets the model decide.
    * ``full``  - applies the full "ladder" ruleset and instructs the
                  model to ship the shortest diff.
    * ``ultra`` - aggressive YAGNI; instructs the model to challenge
                  the rest of the requirement in the same breath.
    """

    OFF = "off"
    LITE = "lite"
    FULL = "full"
    ULTRA = "ultra"

    @classmethod
    def parse(cls, value: str | Intensity | None) -> Intensity:
        """Parse a string into an :class:`Intensity`, falling back to LITE."""
        if value is None or value == "":
            return cls.LITE
        if isinstance(value, cls):
            return value
        try:
            return cls(value.lower())
        except ValueError as exc:
            raise ValueError(
                f"Unknown intensity {value!r}; expected one of "
                f"{', '.join(i.value for i in cls)}"
            ) from exc


@dataclass(frozen=True)
class OptimizedRequest:
    """The output of :meth:`PromptOptimizer.optimize_chat`."""

    request: ChatRequest
    notes: tuple[str, ...] = ()
    intensity: Intensity = Intensity.LITE
    source: str = "ruleset"  # "ruleset" | "external" | "passthrough"


class PromptOptimizer(ABC):
    """Strategy interface for prompt optimization.

    Implementations must be deterministic and side-effect free
    (other than logging), so they can be invoked transparently before
    every model call.
    """

    name: str = "abstract"

    @abstractmethod
    async def optimize_chat(
        self, request: ChatRequest
    ) -> OptimizedRequest:
        """Return an optimized copy of ``request``."""

    async def is_available(self) -> bool:
        """Return whether this optimizer is available to use."""
        return True


class CompositeOptimizer(PromptOptimizer):
    """Pick the right optimizer for the configured :class:`Intensity`."""

    name = "composite"

    def __init__(
        self,
        *,
        intensity: Intensity = Intensity.LITE,
        ruleset: PromptOptimizer | None = None,
        external: PromptOptimizer | None = None,
    ) -> None:
        self._intensity = intensity
        self._ruleset = ruleset
        self._external = external
        self._sync_ruleset_intensity()

    def _sync_ruleset_intensity(self) -> None:
        """Propagate the composite's intensity to the ruleset, if compatible."""
        ruleset = self._ruleset
        if isinstance(ruleset, PonytailRulesetOptimizer):
            ruleset.set_intensity(self._intensity)

    @property
    def intensity(self) -> Intensity:
        return self._intensity

    def set_intensity(self, intensity: Intensity | str) -> None:
        self._intensity = Intensity.parse(intensity)
        # Keep the ruleset in sync so its output reflects the new level
        # when we fall back to it.
        if isinstance(self._ruleset, PonytailRulesetOptimizer):
            self._ruleset.set_intensity(self._intensity)

    async def optimize_chat(self, request: ChatRequest) -> OptimizedRequest:
        if self._intensity is Intensity.OFF:
            return OptimizedRequest(
                request=request,
                notes=("optimizer off",),
                intensity=Intensity.OFF,
                source="passthrough",
            )

        if self._external is not None and await self._external.is_available():
            result = await self._external.optimize_chat(request)
            return OptimizedRequest(
                request=result.request,
                notes=result.notes,
                intensity=self._intensity,
                source="external",
            )

        if self._ruleset is None:
            return OptimizedRequest(
                request=request,
                notes=("no ruleset registered",),
                intensity=self._intensity,
                source="passthrough",
            )

        result = await self._ruleset.optimize_chat(request)
        return OptimizedRequest(
            request=result.request,
            notes=result.notes,
            intensity=self._intensity,
            source="ruleset",
        )


def _ensure_user_message(messages: Sequence[ChatMessage]) -> bool:
    return any(m.role.value == "user" for m in messages)


def _clone_request(request: ChatRequest, messages: Sequence[ChatMessage]) -> ChatRequest:
    """Return a copy of ``request`` with ``messages`` replaced."""
    return request.model_copy(update={"messages": list(messages)})


__all__ = [
    "CompositeOptimizer",
    "Intensity",
    "OptimizedProvider",
    "OptimizedRequest",
    "PonytailCLIOptimizer",
    "PonytailRulesetOptimizer",
    "PromptOptimizer",
]

# Re-export the two concrete implementations and the decorator.
from forgecli.optimizer.ponytail.cli import PonytailCLIOptimizer  # noqa: E402
from forgecli.optimizer.ponytail.decorator import OptimizedProvider  # noqa: E402
from forgecli.optimizer.ponytail.ruleset import PonytailRulesetOptimizer  # noqa: E402
