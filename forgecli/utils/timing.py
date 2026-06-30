"""Simple timing utilities."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def Timer(label: str = "elapsed") -> Iterator[dict[str, Any]]:
    """Context manager that measures wall-clock duration.

    Usage:
        with Timer() as t:
            ...
        print(t["seconds"])
    """
    result: dict[str, Any] = {"label": label, "seconds": 0.0}
    started = time.perf_counter()
    try:
        yield result
    finally:
        result["seconds"] = time.perf_counter() - started
