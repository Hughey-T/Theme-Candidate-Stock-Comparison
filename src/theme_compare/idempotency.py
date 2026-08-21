"""Persistent idempotency records for externally retried v2 POST operations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar

from .models import SemanticError, strict_json_loads
from .storage import StorageError

T = TypeVar("T", bound=dict[str, Any])


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class IdempotencyStore:
    """Crash-safe persistent idempotency records scoped by operation."""

    def __init__(self, root: Path) -> None:
        self.root = (root / ".idempotency").resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def _validate_key(key: str) -> str:
        value = key.strip()
        if not (8 <= len(value) <= 200):
            raise SemanticError("Idempotency-Key must be 8..200 characters")
        return value

    def _record_path(self, scope: str, key: str) -> Path:
        identity = hashlib.sha256(f"{scope}\0{key}".encode()).hexdigest()
        return self.root / f"{identity}.json"

    def execute(
        self,
        scope: str,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[], T],
    ) -> T:
        key = self._validate_key(key)
        payload_sha256 = _canonical_hash(payload)
        path = self._record_path(scope, key)
        lock_path = path.with_suffix(".lock")
        try:
            import fcntl
        except ImportError as exc:  # pragma: no cover - production is Linux container only
            raise StorageError("idempotency locking requires Linux; use Docker Desktop") from exc

        try:
            with lock_path.open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    if path.is_file():
                        record = strict_json_loads(path.read_bytes())
                        if not isinstance(record, dict):
                            raise StorageError("invalid idempotency record")
                        if record.get("payload_sha256") != payload_sha256:
                            raise SemanticError(
                                "Idempotency-Key was already used with a different payload"
                            )
                        result = record.get("result")
                        if not isinstance(result, dict):
                            raise StorageError("invalid idempotency result")
                        return result

                    result = operation()
                    record = {
                        "scope": scope,
                        "key_sha256": hashlib.sha256(key.encode()).hexdigest(),
                        "payload_sha256": payload_sha256,
                        "result": result,
                    }
                    self._atomic_write(path, record)
                    return result
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise StorageError("idempotency storage failure") from exc

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        fd, name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise StorageError("idempotency durability failure") from exc
        finally:
            Path(name).unlink(missing_ok=True)
