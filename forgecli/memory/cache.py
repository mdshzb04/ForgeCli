"""Lightweight in-memory cache with optional TTL.

A future iteration can swap this for SQLite-backed or Redis-backed caching
without affecting call sites.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _Entry(Generic[V]):
    value: V
    expires_at: float | None  # epoch seconds, or None for "no expiry"


class Cache(Generic[K, V]):
    """Thread-safe key/value cache supporting optional per-entry TTL."""

    def __init__(self, *, default_ttl: float | None = None) -> None:
        self._store: dict[K, _Entry[V]] = {}
        self._default_ttl = default_ttl
        self._lock = RLock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at < time.time():
                self._store.pop(key, None)
                return None
            return entry.value

    def set(self, key: K, value: V, *, ttl: float | None = None) -> None:
        effective_ttl = self._default_ttl if ttl is None else ttl
        expires = time.time() + effective_ttl if effective_ttl else None
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=expires)

    def delete(self, key: K) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __contains__(self, key: K) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
