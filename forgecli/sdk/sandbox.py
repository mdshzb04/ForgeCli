"""Plugin sandboxing.

ForgeCLI does *not* run untrusted plugin code in a separate
sandboxed process by default — the plugin ecosystem is meant to
be trusted-but-scoped. This module provides two layers of
protection:

* :class:`ScopedBuiltins` — a stripped-down :data:`builtins`
  dict that does not expose :func:`eval`, :func:`exec`,
  :func:`compile`, or :func:`__import__`. Plugins that need to
  import other plugins must do so at enable-time, not lazily.
* :class:`Sandbox` — a context manager that swaps the host's
  :data:`builtins` for the stripped version while a callback runs.
  The original builtins are restored on exit.

Plugins that request the :attr:`Permission.EXEC` permission bypass
the sandbox (their callbacks run with full builtins). Other
plugins run sandboxed by default.
"""

from __future__ import annotations

import builtins as _builtins
import contextlib
from collections.abc import Callable, Iterator
from typing import Any

from forgecli.sdk.manifest import Permission

# Names that are always available; everything else is dropped.
_ALLOWED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        # Core types
        "object", "type", "super", "property", "classmethod",
        "staticmethod", "isinstance", "issubclass", "callable",
        "id", "hash", "repr", "str", "int", "float", "complex",
        "bool", "list", "tuple", "set", "frozenset", "dict",
        "bytes", "bytearray", "memoryview", "range", "slice",
        "enumerate", "zip", "map", "filter", "reversed",
        "iter", "next", "len", "min", "max", "sum", "abs", "round",
        "pow", "divmod", "all", "any", "sorted",
        # Printing / I/O (controlled)
        "print", "open", "input",
        # Exceptions
        "BaseException", "Exception", "ValueError", "TypeError",
        "KeyError", "IndexError", "StopIteration", "RuntimeError",
        "ImportError", "AttributeError", "NotImplementedError",
        # Names commonly used in tests
        "__name__", "__doc__", "__file__", "__package__",
        # Async
        "asyncio",
    }
)


# Names that the sandbox always *removes*.
_FORBIDDEN_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
    }
)


class ScopedBuiltins:
    """A pre-built :data:`builtins` dict for sandboxed callbacks.

    The ``strict`` mode drops everything that is not in
    :data:`_ALLOWED_BUILTIN_NAMES` *and* removes the always-forbidden
    names. The ``relaxed`` mode keeps most builtins but still
    removes the always-forbidden ones.
    """

    def __init__(self, *, strict: bool = False) -> None:
        self._strict = strict
        self._table: dict[str, Any] = {}
        self._build()

    def _build(self) -> None:
        if self._strict:
            self._table = {
                name: getattr(_builtins, name)
                for name in _ALLOWED_BUILTIN_NAMES
                if hasattr(_builtins, name)
            }
        else:
            # Keep most things, but always drop the forbidden ones.
            self._table = {name: value for name, value in vars(_builtins).items()}
        for name in _FORBIDDEN_BUILTIN_NAMES:
            self._table.pop(name, None)

    @property
    def table(self) -> dict[str, Any]:
        """Return a copy of the scoped builtins table."""
        return dict(self._table)


class Sandbox:
    """Swap the host's :data:`builtins` for a scoped table inside ``with``.

    Example::

        with Sandbox(plugin_permissions=plugin.manifest.permissions):
            plugin.callback(...)

    Plugins that request :attr:`Permission.EXEC` are run with the
    full builtins; everything else runs sandboxed.
    """

    def __init__(
        self,
        *,
        plugin_permissions: tuple[Permission, ...] = (),
        strict: bool = False,
    ) -> None:
        self._scoped = ScopedBuiltins(strict=strict)
        self._plugin_permissions = tuple(plugin_permissions)
        self._original_builtins: dict[str, Any] | None = None

    def __enter__(self) -> None:
        if Permission.EXEC in self._plugin_permissions:
            # Plugin asked for exec; give it the full power.
            return
        # Snapshot the *set* of attribute names *and* their values
        # before we mutate anything. We use ``dir(builtins)`` to
        # enumerate names because the scoped table may have
        # stripped names that ``vars`` depends on.
        self._original_builtins = {name: getattr(_builtins, name) for name in dir(_builtins)}
        # Replace the host builtins module attributes with the
        # scoped table for the duration of the block.
        for name in list(self._original_builtins.keys()):
            if name in self._scoped.table:
                setattr(_builtins, name, self._scoped.table[name])
            else:
                with contextlib.suppress(AttributeError):
                    delattr(_builtins, name)

    def __exit__(self, *exc: Any) -> None:
        if self._original_builtins is None:
            return
        # Remove any names that exist now but did not exist when we
        # entered. We use ``dir`` rather than ``vars`` to enumerate,
        # because ``vars`` itself may have been stripped from the
        # sandbox.
        original = self._original_builtins
        for name in list(dir(_builtins)):
            if name not in original:
                with contextlib.suppress(AttributeError):
                    delattr(_builtins, name)
        # Restore every original name. Even if a name was removed
        # during the block, ``__import__`` is back in the table.
        for name, value in original.items():
            with contextlib.suppress(AttributeError):
                setattr(_builtins, name, value)
        self._original_builtins = None


@contextlib.contextmanager
def sandbox(
    *,
    plugin_permissions: tuple[Permission, ...] = (),
    strict: bool = False,
) -> Iterator[None]:
    """Functional form of :class:`Sandbox`."""
    sb = Sandbox(plugin_permissions=plugin_permissions, strict=strict)
    sb.__enter__()
    try:
        yield
    finally:
        sb.__exit__(None, None, None)


def run_sandboxed(
    callback: Callable[..., Any],
    *args: Any,
    plugin_permissions: tuple[Permission, ...] = (),
    strict: bool = False,
    **kwargs: Any,
) -> Any:
    """Run ``callback(*args, **kwargs)`` inside a sandbox."""
    with sandbox(plugin_permissions=plugin_permissions, strict=strict):
        return callback(*args, **kwargs)


__all__ = [
    "Sandbox",
    "ScopedBuiltins",
    "run_sandboxed",
    "sandbox",
]
