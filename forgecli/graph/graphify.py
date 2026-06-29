"""Thin wrapper around the Graphify CLI.

Graphify is an external tool installed as ``graphify`` on the user's PATH
(typically via ``uv tool install graphifyy``). This module:

* detects whether ``graphify`` is installed;
* invokes it as an async subprocess (never imports its Python package);
* parses the resulting ``graph.json`` and ``manifest.json`` into typed
  dataclasses that satisfy the :mod:`forgecli.graph.repository` interface.

The CLI surface we use is intentionally small:

* ``graphify .``         - default full extraction (alias for ``extract``)
* ``graphify extract``   - same thing, with extra flags
* ``graphify query``     - free-form BFS/DFS question
* ``graphify explain``   - plain-language explanation
* ``graphify path``      - shortest path between two nodes
* ``graphify affected``  - reverse-traversal blast radius
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from forgecli.core.errors import ForgeCLIError

DEFAULT_OUTPUT_DIR = "graphify-out"
DEFAULT_GRAPH_FILE = "graph.json"
DEFAULT_MANIFEST_FILE = "manifest.json"


class GraphifyNotFoundError(ForgeCLIError):
    """Raised when the ``graphify`` executable is not on the user's PATH."""


class GraphifyInvocationError(ForgeCLIError):
    """Raised when the ``graphify`` subprocess exits with a non-zero status."""


@dataclass(frozen=True)
class GraphifyArtifacts:
    """Filesystem locations of the artifacts produced by Graphify."""

    root: Path
    output_dir: Path
    graph_json: Path
    manifest_json: Path

    @classmethod
    def for_root(cls, root: Path) -> GraphifyArtifacts:
        out = root / DEFAULT_OUTPUT_DIR
        return cls(
            root=root,
            output_dir=out,
            graph_json=out / DEFAULT_GRAPH_FILE,
            manifest_json=out / DEFAULT_MANIFEST_FILE,
        )


class GraphifyClient:
    """Async subprocess wrapper around the ``graphify`` CLI.

    Instances are cheap to construct; they do not touch the filesystem
    until :meth:`detect`, :meth:`build`, :meth:`query`, etc. are called.
    """

    def __init__(
        self,
        *,
        executable: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        self._executable = executable or os.environ.get("FORGECLI_GRAPHIFY_BIN", "graphify")
        self._timeout = timeout

    @property
    def executable(self) -> str:
        return self._executable

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    async def detect(self) -> str | None:
        """Return the resolved path of the ``graphify`` binary, or ``None``."""
        path = shutil.which(self._executable)
        return path

    async def is_installed(self) -> bool:
        """Return True if ``graphify`` is on the user's PATH."""
        return await self.detect() is not None

    async def version(self) -> str:
        """Return the version string reported by ``graphify --version``."""
        binary = await self.detect()
        if binary is None:
            raise GraphifyNotFoundError(
                f"Graphify executable {self._executable!r} not found on PATH"
            )
        proc = await asyncio.create_subprocess_exec(
            binary,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:  # pragma: no cover - graphify exits 0 on --version
            raise GraphifyInvocationError(
                f"graphify --version failed: {stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode(errors="replace").strip() or "unknown"

    # ------------------------------------------------------------------
    # Build / update
    # ------------------------------------------------------------------

    async def build(
        self,
        root: Path,
        *,
        force: bool = False,
        no_cluster: bool = False,
        extra_args: Iterable[str] = (),
    ) -> GraphifyBuildOutcome:
        """Run ``graphify extract <root>`` and return the parsed outcome.

        The default subcommand (``graphify .``) is a thin alias for
        ``extract``; we use ``extract`` explicitly so we can pass flags
        like ``--no-cluster`` and ``--force`` deterministically.
        """
        binary = await self.detect()
        if binary is None:
            raise GraphifyNotFoundError(
                f"Graphify executable {self._executable!r} not found on PATH"
            )

        root = root.resolve()
        args: list[str] = [
            binary,
            "extract",
            str(root),
            "--out",
            str(root),
        ]
        if force:
            args.append("--force")
        if no_cluster:
            args.append("--no-cluster")
        args.extend(extra_args)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(root),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except TimeoutError as exc:
            proc.kill()
            raise GraphifyInvocationError(
                f"graphify extract timed out after {self._timeout}s"
            ) from exc

        if proc.returncode != 0:
            raise GraphifyInvocationError(
                "graphify extract failed (exit "
                f"{proc.returncode}):\n{stderr.decode(errors='replace').strip()}"
            )

        artifacts = GraphifyArtifacts.for_root(root)
        return GraphifyBuildOutcome(
            root=root,
            artifacts=artifacts,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )

    # ------------------------------------------------------------------
    # JSON parsers
    # ------------------------------------------------------------------

    @staticmethod
    def load_graph(path: Path) -> dict[str, Any]:
        """Read and return the raw ``graph.json`` payload."""
        if not path.exists():
            raise FileNotFoundError(f"graph.json not found at {path}")
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def load_manifest(path: Path) -> dict[str, Any]:
        """Read and return the raw ``manifest.json`` payload (may be missing)."""
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # Query / explain / path / affected
    # ------------------------------------------------------------------

    async def _run_capture(
        self,
        root: Path,
        args: list[str],
        *,
        timeout: float | None = None,
    ) -> str:
        binary = await self.detect()
        if binary is None:
            raise GraphifyNotFoundError(
                f"Graphify executable {self._executable!r} not found on PATH"
            )
        proc = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(root),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self._timeout
            )
        except TimeoutError as exc:
            proc.kill()
            raise GraphifyInvocationError(
                f"graphify {' '.join(args[:1])} timed out"
            ) from exc
        if proc.returncode != 0:
            raise GraphifyInvocationError(
                f"graphify exited with {proc.returncode}: "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode(errors="replace")

    async def query(
        self,
        root: Path,
        question: str,
        *,
        budget: int = 2000,
        graph_path: Path | None = None,
        dfs: bool = False,
    ) -> str:
        """Run ``graphify query "<question>"`` and return its stdout text."""
        args: list[str] = ["query", question, "--budget", str(budget)]
        if graph_path is not None:
            args += ["--graph", str(graph_path)]
        if dfs:
            args.append("--dfs")
        return await self._run_capture(root, args)

    async def explain(
        self,
        root: Path,
        target: str,
        *,
        graph_path: Path | None = None,
    ) -> str:
        """Run ``graphify explain "<target>"`` and return its stdout text."""
        args: list[str] = ["explain", target]
        if graph_path is not None:
            args += ["--graph", str(graph_path)]
        return await self._run_capture(root, args)

    async def path(
        self,
        root: Path,
        a: str,
        b: str,
        *,
        graph_path: Path | None = None,
    ) -> str:
        """Run ``graphify path "<a>" "<b>"`` and return its stdout text."""
        args: list[str] = ["path", a, b]
        if graph_path is not None:
            args += ["--graph", str(graph_path)]
        return await self._run_capture(root, args)

    async def affected(
        self,
        root: Path,
        target: str,
        *,
        relation: Iterable[str] | None = None,
        depth: int = 2,
        graph_path: Path | None = None,
    ) -> str:
        """Run ``graphify affected "<target>"`` and return its stdout text."""
        args: list[str] = ["affected", target, "--depth", str(depth)]
        for rel in relation or ():
            args += ["--relation", rel]
        if graph_path is not None:
            args += ["--graph", str(graph_path)]
        return await self._run_capture(root, args)


@dataclass(frozen=True)
class GraphifyBuildOutcome:
    """The captured result of a ``graphify extract`` invocation."""

    root: Path
    artifacts: GraphifyArtifacts
    stdout: str
    stderr: str

    @property
    def graph_payload(self) -> dict[str, Any]:
        """The parsed ``graph.json`` payload (reads from disk on each call)."""
        return GraphifyClient.load_graph(self.artifacts.graph_json)

    @property
    def manifest_payload(self) -> dict[str, Any]:
        """The parsed ``manifest.json`` payload (may be empty)."""
        return GraphifyClient.load_manifest(self.artifacts.manifest_json)


__all__ = [
    "DEFAULT_GRAPH_FILE",
    "DEFAULT_MANIFEST_FILE",
    "DEFAULT_OUTPUT_DIR",
    "GraphifyArtifacts",
    "GraphifyBuildOutcome",
    "GraphifyClient",
    "GraphifyInvocationError",
    "GraphifyNotFoundError",
]
