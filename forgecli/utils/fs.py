"""Filesystem helpers (sync)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path


def ensure_dir(path: os.PathLike[str] | str) -> Path:
    """Create ``path`` (and parents) if missing; return the resolved Path."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_text(path: os.PathLike[str] | str, *, encoding: str = "utf-8") -> str:
    """Read text from ``path`` and return it as a string."""
    return Path(path).read_text(encoding=encoding)


def write_text(
    path: os.PathLike[str] | str,
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Write ``content`` to ``path``, creating parent directories as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return p


def atomic_write(
    path: os.PathLike[str] | str,
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Atomically write ``content`` to ``path`` via a temporary file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return target


def iter_files(root: os.PathLike[str] | str, patterns: Iterable[str]) -> Iterable[Path]:
    """Yield files under ``root`` matching any of the given glob ``patterns``."""
    base = Path(root)
    for pattern in patterns:
        yield from base.glob(pattern)
