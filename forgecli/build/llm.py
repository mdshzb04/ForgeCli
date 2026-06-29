"""Stage 3 — LLM call.

Assembles the final prompt (Ponytail-optimized system + user, plus
Graphify retrieval as context) and dispatches it through the active
provider. The selected provider is the one chosen by the router (see
:mod:`forgecli.providers.router`).
"""

from __future__ import annotations

import asyncio

from forgecli.build import BuildContext
from forgecli.providers.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    Provider,
    Role,
)


_SYSTEM_PROMPT = (
    "You are a senior software engineer. Apply the Ponytail ruleset:\n"
    "  1. Speculative need = skip it (YAGNI).\n"
    "  2. Reuse the helper/pattern that already lives in the codebase.\n"
    "  3. Use the standard library.\n"
    "  4. Native platform feature > third-party library.\n"
    "  5. Use an already-installed dependency before adding a new one.\n"
    "  6. One line beats many.\n"
    "  7. Only then: the minimum code that works.\n\n"
    "Return ONLY a unified diff in the response. No prose, no explanation, "
    "no code fences. The diff must apply with `git apply`."
)


async def llm_call(context: BuildContext) -> BuildContext:
    """Send the assembled prompt to the active provider and store the response."""
    provider: Provider | None = context.extras.get("provider")
    if provider is None:
        raise RuntimeError("no provider wired into the build context")

    user_content = _format_user_prompt(context)
    base_request: ChatRequest = context.optimized_request or ChatRequest(
        messages=[ChatMessage(role=Role.USER, content=context.prompt)]
    )
    request = base_request.model_copy(
        update={
            "model": context.decision.model if context.decision else None,
            "messages": _assemble_messages(base_request.messages, user_content),
        }
    )

    response: ChatResponse = await provider.chat(request)
    context.response = response
    return context


def _format_user_prompt(context: BuildContext) -> str:
    parts: list[str] = [context.prompt]
    if context.retrieval:
        parts.append("\n" + context.retrieval)
    parts.append(
        "\nRespond with a unified diff only. "
        "Use the file paths implied by the retrieval above. "
        "Do not include prose."
    )
    return "\n".join(parts)


def _assemble_messages(
    base: list[ChatMessage], user_content: str
) -> list[ChatMessage]:
    """Insert the system prompt at the head, replace the user message.

    Ponytail prepended a system message of its own; we layer our
    strict diff-formatting instruction on top by *replacing* the first
    user message with our assembled content.
    """
    out: list[ChatMessage] = []
    replaced_user = False
    for message in base:
        if not replaced_user and message.role is Role.USER:
            out.append(ChatMessage(role=Role.USER, content=user_content))
            replaced_user = True
            continue
        if message.role is Role.SYSTEM:
            # Keep the Ponytail guidance; append our diff-formatting rule.
            extra = "\n\n" + _SYSTEM_PROMPT
            out.append(
                ChatMessage(
                    role=Role.SYSTEM,
                    content=message.content + extra,
                )
            )
            continue
        out.append(message)
    if not replaced_user:
        out.append(ChatMessage(role=Role.USER, content=user_content))
    return out


__all__ = ["llm_call"]


# Silence unused-import warnings for symbols only used in some branches.
_ = asyncio
