"""Identifier generation helpers."""

from __future__ import annotations

import secrets


def new_id(prefix: str = "id", *, length: int = 12) -> str:
    """Return a short URL-safe unique identifier, optionally prefixed."""
    body = secrets.token_hex(length)
    return f"{prefix}_{body}" if prefix else body
