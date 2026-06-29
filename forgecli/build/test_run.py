"""Stage 6 — run tests.

Runs an optional test command (default: ``pytest -q``) under the
project root and captures stdout/stderr/return code. The build does
not fail when tests fail — failures are recorded in the context and
surfaced in the summary.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from forgecli.build import BuildContext


DEFAULT_TEST_COMMAND = "pytest -q"


async def run_tests(context: BuildContext) -> BuildContext:
    """Execute the test command and record the outcome."""
    command = context.extras.get("test_command") or DEFAULT_TEST_COMMAND
    if not shutil.which(command.split()[0]):
        context.test_stdout = ""
        context.test_stderr = f"`{command.split()[0]}` not found on PATH; skipping tests."
        context.test_returncode = None
        return context

    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(context.root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_timeout_for(context)
        )
    except asyncio.TimeoutError:
        proc.kill()
        context.test_stdout = ""
        context.test_stderr = "tests timed out"
        context.test_returncode = 124
        return context
    context.test_stdout = stdout.decode(errors="replace")
    context.test_stderr = stderr.decode(errors="replace")
    context.test_returncode = proc.returncode
    return context


def _timeout_for(context: BuildContext) -> float:
    timeout = context.extras.get("test_timeout")
    if isinstance(timeout, (int, float)):
        return float(timeout)
    return 120.0


def run_subprocess_sync(command: str, root: Path, *, timeout: float) -> subprocess.CompletedProcess:
    """Synchronous helper used by tests."""
    return subprocess.run(
        command,
        cwd=str(root),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


__all__ = ["DEFAULT_TEST_COMMAND", "run_subprocess_sync", "run_tests"]
