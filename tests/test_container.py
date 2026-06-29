"""Tests for the dependency injection container."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from forgecli.core.container import Container


@dataclass
class _Service:
    name: str


def test_register_singleton_caches() -> None:
    container = Container()
    counter = {"n": 0}

    def factory(c: Container) -> _Service:
        counter["n"] += 1
        return _Service(name="x")

    container.register(_Service, factory)
    a = container.resolve(_Service)
    b = container.resolve(_Service)
    assert a is b
    assert counter["n"] == 1


def test_register_non_singleton() -> None:
    container = Container()
    container.register(_Service, lambda _c: _Service(name="x"), singleton=False)
    a = container.resolve(_Service)
    b = container.resolve(_Service)
    assert a is not b


def test_resolve_unknown_raises() -> None:
    container = Container()

    class _Unknown:
        pass

    with pytest.raises(KeyError):
        container.resolve(_Unknown)


def test_has_and_clear() -> None:
    container = Container()
    container.register(_Service, lambda _c: _Service(name="x"))
    assert container.has(_Service)
    container.clear()
    assert not container.has(_Service)
