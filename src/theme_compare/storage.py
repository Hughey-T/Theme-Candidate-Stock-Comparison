"""Linux-container JSON storage with one validated durability transaction path."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol, TypeVar

from .models import SemanticError, strict_json_loads
from .state import StateMachine

_SESSION = re.compile(r"^s_[0-9a-f]{32}$")
T = TypeVar("T")
Mutation = Callable[[dict[str, Any]], tuple[dict[str, Any], T]]


class StorageError(RuntimeError):
    """A terminal storage or persisted-integrity failure."""


class SessionStorage(Protocol):
    def create(self, session_id: str, state: dict[str, Any]) -> None: ...
    def load(self, session_id: str) -> dict[str, Any]: ...
    def transaction(self, session_id: str, mutation: Mutation[T]) -> T: ...
    def health(self) -> bool: ...


class JsonVolumeStorage:
    """Persistent-volume backend; production support is Linux container only."""

    def __init__(self, root: Path, *, create_root: bool = True) -> None:
        self.root = root.resolve()
        if create_root:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, session_id: str) -> Path:
        if not _SESSION.fullmatch(session_id):
            raise SemanticError("invalid session_id")
        return self.root / f"{session_id}.json"

    @contextmanager
    def locked(self, session_id: str) -> Iterator[None]:
        # Deliberately lazy: importing the package works on Windows; runtime execution is via Docker.
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - Windows policy is tested structurally
            raise StorageError("direct runtime locking requires Linux; use Docker Desktop") from exc
        lock = self.path(session_id).with_suffix(".lock")
        try:
            with lock.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise StorageError("storage lock failure") from exc

    def create(self, session_id: str, state: dict[str, Any]) -> None:
        path = self.path(session_id)
        with self.locked(session_id):
            if path.exists():
                raise SemanticError("session already exists")
            self._validate_candidate(state)
            self._atomic_write(path, state)
            self._verify(path)

    def load(self, session_id: str) -> dict[str, Any]:
        path = self.path(session_id)
        if not path.is_file():
            raise FileNotFoundError(session_id)
        try:
            return StateMachine(path).load()
        except (OSError, ValueError) as exc:
            raise StorageError("persisted state integrity validation failed") from exc

    def transaction(self, session_id: str, mutation: Mutation[T]) -> T:
        path = self.path(session_id)
        with self.locked(session_id):
            if not path.is_file():
                raise FileNotFoundError(session_id)
            try:
                original = path.read_bytes()
                current = strict_json_loads(original)
                if not isinstance(current, dict):
                    raise SemanticError("persisted state is not an object")
                StateMachine(path).load()
            except (OSError, ValueError) as exc:
                raise StorageError("persisted state integrity validation failed") from exc
            proposed, result = mutation(current)
            self._validate_candidate(proposed)
            self._atomic_write(path, proposed)
            self._verify(path)
            return result

    def transition(
        self, state: dict[str, Any], operation: str, artifact: dict[str, Any]
    ) -> dict[str, Any]:
        """Run the existing state machine against an unpublished temporary state."""
        fd, name = tempfile.mkstemp(prefix=".transition.", suffix=".json", dir=self.root)
        os.close(fd)
        temporary = Path(name)
        try:
            temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            return StateMachine(temporary).command(operation, artifact)
        finally:
            temporary.unlink(missing_ok=True)
            temporary.with_suffix(".tmp").unlink(missing_ok=True)

    def _validate_candidate(self, state: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=".validate.", suffix=".json", dir=self.root)
        os.close(fd)
        temporary = Path(name)
        try:
            temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            StateMachine(temporary).load()
        finally:
            temporary.unlink(missing_ok=True)

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
        except OSError as exc:
            raise StorageError("storage durability failure") from exc
        finally:
            Path(name).unlink(missing_ok=True)

    def _verify(self, path: Path) -> None:
        try:
            StateMachine(path).load()
        except (OSError, ValueError) as exc:
            raise StorageError("post-write integrity verification failed") from exc

    def health(self) -> bool:
        if not self.root.is_dir():
            return False
        try:
            fd, name = tempfile.mkstemp(prefix=".health.", dir=self.root)
            os.close(fd)
            Path(name).unlink()
            return True
        except OSError:
            return False
