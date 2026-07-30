"""Small, dependency-light domain helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any


class SemanticError(ValueError):
    """An artifact is structurally valid but semantically unsafe."""


def require_rfc3339(value: str) -> None:
    if not re.search(r"(Z|[+-]\d\d:\d\d)$", value):
        raise SemanticError(f"timezone required: {value}")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SemanticError(f"invalid RFC3339 timestamp: {value}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise SemanticError(f"{name} must be finite")


def candidate_set_id(candidates: list[dict[str, Any]]) -> str:
    """Order-independent ID; identity changes cannot silently retain the set ID."""
    identities = sorted(c["candidate_id"] for c in candidates)
    return "cs_" + canonical_hash(identities)[:24]
