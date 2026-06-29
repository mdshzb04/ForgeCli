"""Thin wrapper around GitPython's :class:`Repo`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from git import Repo as _PyRepo
from git.exc import GitError as _PyGitError

from forgecli.core.errors import GitError


class GitRepo:
    """Wrapper around GitPython's :class:`Repo` with typed errors."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        try:
            self._repo = _PyRepo(str(self._path))
        except _PyGitError as exc:
            raise GitError(f"Not a git repository: {self._path}") from exc
        except Exception as exc:
            raise GitError(f"Failed to open repository at {self._path}: {exc}") from exc

    @property
    def path(self) -> Path:
        return self._path

    @property
    def raw(self) -> _PyRepo:
        return self._repo

    @property
    def head(self) -> str:
        try:
            return str(self._repo.head.commit)
        except _PyGitError as exc:
            raise GitError(f"Unable to read HEAD: {exc}") from exc

    def is_clean(self) -> bool:
        return not self._repo.is_dirty(untracked_files=True)

    def status(self) -> dict[str, Any]:
        """Return a small status summary; placeholder for richer UX."""
        return {
            "branch": self._safe_branch(),
            "clean": self.is_clean(),
        }

    def _safe_branch(self) -> str:
        try:
            return self._repo.active_branch.name
        except Exception:
            return "detached"
