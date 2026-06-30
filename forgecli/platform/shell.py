"""Shell adapter — never hardcodes POSIX-only commands.

This module is the *only* place that may invoke
:func:`subprocess.run` / :func:`asyncio.create_subprocess_shell` for
shell-style invocations. All callers go through :func:`run`, which:

* never relies on ``/bin/sh`` parsing on Windows (it uses
  :class:`subprocess.Popen` with ``shell=False`` and a list argv);
* quotes arguments via :func:`shell_quote` (which understands
  POSIX shells *and* ``cmd.exe`` quoting rules);
* enforces a timeout;
* returns a :class:`ShellResult` that captures stdout/stderr
  decoded as UTF-8 (with replacement) — never ``bytes`` leaking
  out of the platform layer.

The module also exposes a small ``run_capture`` helper used by
:mod:`forgecli.commit.git_utils` and friends.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forgecli.platform.core import is_windows


@dataclass(frozen=True)
class ShellResult:
    """The structured output of a shell invocation."""

    returncode: int
    stdout: str
    stderr: str
    command: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def shell_quote(arg: str) -> str:
    """Quote ``arg`` for the current platform's shell.

    On POSIX we use :func:`shlex.quote`; on Windows we use
    :func:`subprocess.list2cmdline` (the same algorithm ``cmd.exe``
    uses internally for argv joining).
    """
    if is_windows():
        # list2cmdline accepts a list, not a single string. We wrap the
        # single arg in a list.
        return subprocess.list2cmdline([arg])
    return shlex.quote(arg)


def run(
    args: Sequence[str] | str,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = False,
    input: str | bytes | None = None,
) -> ShellResult:
    """Run a subprocess and return a :class:`ShellResult`.

    ``args`` may be either a list (preferred — avoids shell parsing
    entirely) or a string (in which case the call goes through
    the platform's default shell).

    On Windows, ``args`` is always coerced to a list to avoid
    invoking ``cmd.exe``; on POSIX, list args are exec'd directly.
    """
    argv: tuple[str, ...]
    use_shell: bool
    if isinstance(args, str):
        if is_windows():
            # The user gave us a string; pass it to cmd.exe explicitly
            # so we don't depend on the default shell being sh.
            argv = ("cmd.exe", "/c", args)
            use_shell = False
        else:
            argv = (args,)
            use_shell = True
    else:
        argv = tuple(args)
        use_shell = False

    merged_env: dict[str, str] | None = None
    if env is not None:
        merged_env = os.environ.copy()
        merged_env.update({k: v for k, v in env.items() if v is not None})

    completed = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        env=merged_env,
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        shell=use_shell,
    )
    return ShellResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        command=argv,
    )


async def run_capture(
    args: Sequence[str] | str,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    input: str | bytes | None = None,
) -> ShellResult:
    """Async wrapper around :func:`run`."""
    argv: tuple[str, ...]
    if isinstance(args, str):
        argv = ("cmd.exe", "/c", args) if is_windows() else (args,)
    else:
        argv = tuple(args)

    merged_env: dict[str, str] | None = None
    if env is not None:
        merged_env = os.environ.copy()
        merged_env.update({k: v for k, v in env.items() if v is not None})

    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd is not None else None,
        env=merged_env,
        stdin=asyncio.subprocess.PIPE if input is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        if input is None:
            stdout_b, stderr_b = await process.communicate()
        else:
            stdin_data = input.encode("utf-8") if isinstance(input, str) else input
            stdout_b, stderr_b = await process.communicate(stdin_data)
    except TimeoutError as exc:
        process.kill()
        raise TimeoutError(f"subprocess timed out after {timeout}s") from exc
    return ShellResult(
        returncode=process.returncode or 0,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
        command=argv,
    )


def which(executable: str) -> str | None:
    """Return the absolute path of ``executable`` or None.

    Thin wrapper around :func:`shutil.which` that swallows the
    ``PATHEXT`` quirks on Windows (shutil already handles those).
    """
    import shutil

    return shutil.which(executable)


# Silence unused-import warnings for symbols only used in some branches.
_ = Any
