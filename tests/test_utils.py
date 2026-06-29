"""Tests for utility helpers."""

from __future__ import annotations

import time
from pathlib import Path

from forgecli.utils.fs import atomic_write, ensure_dir, read_text, write_text
from forgecli.utils.ids import new_id
from forgecli.utils.io import aio_read_text, aio_write_text
from forgecli.utils.timing import Timer


def test_ensure_dir_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    result = ensure_dir(target)
    assert result.is_dir()


def test_write_and_read_text(tmp_path: Path) -> None:
    path = write_text(tmp_path / "f.txt", "hello")
    assert read_text(path) == "hello"


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    path = atomic_write(tmp_path / "atomic.txt", "x")
    assert read_text(path) == "x"


def test_new_id_is_unique() -> None:
    ids = {new_id("n") for _ in range(50)}
    assert len(ids) == 50


def test_timer_measures_duration() -> None:
    with Timer() as t:
        time.sleep(0.01)
    assert t["seconds"] >= 0.01


def test_aio_helpers_round_trip(tmp_path: Path) -> None:
    import asyncio

    target = tmp_path / "aio.txt"
    asyncio.run(aio_write_text(target, "data"))
    content = asyncio.run(aio_read_text(target))
    assert content == "data"
