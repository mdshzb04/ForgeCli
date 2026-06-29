"""High-level git operations: stage, commit, branch, push, diff."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from forgecli.core.errors import GitError
from forgecli.core.service import Service
from forgecli.git.commit import CommitAuthor, CommitInfo
from forgecli.git.repo import GitRepo


class GitService(Service):
    """Convenience operations built on top of :class:`GitRepo`."""

    name = "git.service"

    def __init__(
        self,
        repo: GitRepo,
        *,
        default_branch: str = "main",
        author: CommitAuthor | None = None,
    ) -> None:
        super().__init__()
        self._repo = repo
        self._default_branch = default_branch
        self._author = author

    @property
    def repo(self) -> GitRepo:
        return self._repo

    def stage(self, paths: Iterable[str | Path]) -> None:
        """Add ``paths`` to the index."""
        try:
            self._repo.raw.index.add([str(p) for p in paths])
        except Exception as exc:
            raise GitError(f"Failed to stage files: {exc}") from exc

    def commit(
        self,
        message: str,
        *,
        author: CommitAuthor | None = None,
        all_files: bool = False,
    ) -> CommitInfo:
        """Create a commit with ``message``; placeholder for now."""
        raise NotImplementedError("GitService.commit() is a scaffold placeholder")

    def current_branch(self) -> str:
        return self._repo._safe_branch()

    def diff(self, *args: Any) -> str:
        """Return ``git diff`` output; placeholder."""
        raise NotImplementedError("GitService.diff() is a scaffold placeholder")
