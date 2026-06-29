"""SQLite-backed local memory store (singleton lifecycle owned by AppContext)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from forgecli.utils.fs import ensure_dir


class MemoryStore:
    """Thin wrapper around a local SQLite database.

    The store is intentionally minimal: it owns the connection and provides
    a few named-table helpers. Higher-level repositories (e.g. history)
    layer domain logic on top.
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        ensure_dir(self._db_path.parent)
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connect(self) -> None:
        """Open the database and run schema migrations."""
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we use explicit transactions
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def close(self) -> None:
        """Close the underlying connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> MemoryStore:
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("MemoryStore.connect() must be called first")
        return self._conn

    def _migrate(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        row = self.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(self.SCHEMA_VERSION),),
            )
        # Future migrations can be chained here by inspecting ``row``.

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        return self.conn.executemany(sql, params)
