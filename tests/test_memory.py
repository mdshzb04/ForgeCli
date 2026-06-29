"""Tests for the SQLite-backed memory store and history repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgecli.memory.history import HistoryRepository
from forgecli.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    s = MemoryStore(tmp_path / "history.db")
    s.connect()
    yield s
    s.close()


def test_schema_meta_initialized(store: MemoryStore) -> None:
    row = store.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
    assert row is not None
    assert row["value"] == str(MemoryStore.SCHEMA_VERSION)


def test_history_record_and_list(store: MemoryStore) -> None:
    history = HistoryRepository(store, history_limit=10)
    id_ = history.record(command="plan run hello", provider="mock", model="mock-model", success=True)
    assert id_ > 0
    entries = history.list_recent(limit=5)
    assert len(entries) == 1
    assert entries[0].command == "plan run hello"
    assert entries[0].provider == "mock"


def test_history_trims_to_limit(store: MemoryStore) -> None:
    history = HistoryRepository(store, history_limit=3)
    for i in range(5):
        history.record(command=f"cmd {i}")
    entries = history.list_recent(limit=10)
    assert len(entries) == 3
    commands = [e.command for e in entries]
    assert "cmd 4" in commands
    assert "cmd 0" not in commands
