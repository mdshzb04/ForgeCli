"""Async filesystem helpers."""

from __future__ import annotations

import os
from pathlib import Path

import aiofiles


async def aio_read_text(path: os.PathLike[str] | str, *, encoding: str = "utf-8") -> str:
    """Asynchronously read text from ``path``."""
    async with aiofiles.open(path, encoding=encoding) as fh:
        return await fh.read()


async def aio_write_text(
    path: os.PathLike[str] | str,
    content: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Asynchronously write text to ``path``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target, mode="w", encoding=encoding) as fh:
        await fh.write(content)
