"""Replaceable, crash-safe JSON session storage."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

import fcntl

from .models import SemanticError
from .state import StateMachine

_SESSION = re.compile(r"^s_[0-9a-f]{32}$")


class SessionStorage(Protocol):
    def create(self, session_id: str, state: dict[str, Any]) -> None: ...
    def load(self, session_id: str) -> dict[str, Any]: ...
    def path(self, session_id: str) -> Path: ...
    def locked(self, session_id: str) -> Iterator[None]: ...
    def health(self) -> dict[str, Any]: ...


class JsonVolumeStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, session_id: str) -> Path:
        if not _SESSION.fullmatch(session_id):
            raise SemanticError("invalid session_id")
        # Hash-shaped IDs are validated before being mapped into the storage root.
        return self.root / f"{session_id}.json"

    @contextmanager
    def locked(self, session_id: str) -> Iterator[None]:
        path = self.path(session_id)
        lock = path.with_suffix(".lock")
        with lock.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def create(self, session_id: str, state: dict[str, Any]) -> None:
        path = self.path(session_id)
        with self.locked(session_id):
            if path.exists():
                raise SemanticError("session already exists")
            self._atomic_write(path, state)
            StateMachine(path).load()

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.path(session_id)
        if not path.is_file():
            raise FileNotFoundError(session_id)
        # Always parse and validate persisted bytes; there is no memory cache or fallback.
        return StateMachine(path).load()

    def _atomic_write(self, path: Path, state: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, path)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def health(self) -> dict[str, Any]:
        probe = self.root / ".health"
        try:
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
            return {"status": "ok", "root_writable": True}
        except OSError:
            return {"status": "unhealthy", "root_writable": False}
