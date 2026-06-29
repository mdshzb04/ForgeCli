"""Lightweight dependency-injection container."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class Container:
    """A minimal service container with factory and singleton registrations.

    The container intentionally avoids any global state; an instance is
    owned by :class:`forgecli.core.context.AppContext` and created per process.
    """

    def __init__(self) -> None:
        self._factories: dict[type, Callable[[Container], Any]] = {}
        self._singletons: dict[type, Any] = {}
        self._singleton_flags: dict[type, bool] = {}

    def register(
        self,
        interface: type[T],
        factory: Callable[[Container], T],
        *,
        singleton: bool = True,
    ) -> None:
        """Register a factory for ``interface``.

        When ``singleton`` is True, the first call to :meth:`resolve` will
        cache the result and return it for all subsequent calls.
        """
        self._factories[interface] = factory
        self._singleton_flags[interface] = singleton
        if not singleton:
            self._singletons.pop(interface, None)

    def register_instance(self, interface: type[T], instance: T) -> None:
        """Bind a pre-constructed instance to ``interface``."""
        self._factories[interface] = lambda _c: instance
        self._singletons[interface] = instance
        self._singleton_flags[interface] = True

    def resolve(self, interface: type[T]) -> T:
        """Resolve an instance for ``interface``."""
        if interface in self._singletons:
            return self._singletons[interface]  # type: ignore[return-value]
        if interface not in self._factories:
            raise KeyError(f"No registration for {interface!r}")
        instance = self._factories[interface](self)
        if self._is_singleton(interface):
            self._singletons[interface] = instance
        return instance  # type: ignore[return-value]

    def _is_singleton(self, interface: type) -> bool:
        """Return True if ``interface`` was registered as a singleton."""
        return self._singleton_flags.get(interface, True)

    def has(self, interface: type) -> bool:
        return interface in self._factories or interface in self._singletons

    def clear(self) -> None:
        """Drop all registrations and cached singletons."""
        self._factories.clear()
        self._singletons.clear()
        self._singleton_flags.clear()
