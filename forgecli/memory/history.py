"""Append-only history of CLI invocations and AI interactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from forgecli.memory.store import MemoryStore


@dataclass(frozen=True)
class HistoryEntry:
    """A single persisted history record."""

    id: int
    timestamp: datetime
    command: str
    provider: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    success: bool
    error: str | None


class HistoryRepository:
    """Persistence of CLI/AI invocations keyed by time."""

    def __init__(self, store: MemoryStore, *, history_limit: int = 1000) -> None:
        self._store = store
        self._limit = history_limit
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._store.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                command TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 1,
                error TEXT
            )
            """
        )
        self._store.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts DESC)"
        )

    def record(
        self,
        *,
        command: str,
        provider: str | None = None,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> int:
        """Insert a new history row and return its id."""
        cursor = self._store.execute(
            """
            INSERT INTO history (
                ts, command, provider, model,
                prompt_tokens, completion_tokens,
                duration_ms, success, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                command,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                duration_ms,
                int(success),
                error,
            ),
        )
        self._trim()
        return int(cursor.lastrowid or 0)

    def list_recent(self, limit: int = 50) -> list[HistoryEntry]:
        """Return the most recent history entries (newest first)."""
        rows = self._store.execute(
            """
            SELECT id, ts, command, provider, model,
                   prompt_tokens, completion_tokens,
                   duration_ms, success, error
            FROM history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._to_entry(r) for r in rows]

    def _trim(self) -> None:
        """Drop oldest rows past the configured retention limit."""
        row = self._store.execute("SELECT COUNT(*) AS n FROM history").fetchone()
        total = int(row["n"]) if row else 0
        if total <= self._limit:
            return
        excess = total - self._limit
        self._store.execute(
            """
            DELETE FROM history
            WHERE id IN (
                SELECT id FROM history ORDER BY id ASC LIMIT ?
            )
            """,
            (excess,),
        )

    @staticmethod
    def _to_entry(row: Any) -> HistoryEntry:
        return HistoryEntry(
            id=int(row["id"]),
            timestamp=datetime.fromisoformat(row["ts"]),
            command=str(row["command"]),
            provider=row["provider"],
            model=row["model"],
            prompt_tokens=int(row["prompt_tokens"] or 0),
            completion_tokens=int(row["completion_tokens"] or 0),
            duration_ms=int(row["duration_ms"] or 0),
            success=bool(row["success"]),
            error=row["error"],
        )
