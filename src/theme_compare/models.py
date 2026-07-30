"""Small, dependency-light domain helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


class SemanticError(ValueError):
    """An artifact is structurally valid but semantically unsafe."""


def parse_rfc3339(value: str) -> datetime:
    """Parse an RFC 3339 instant and normalize it to UTC."""
    if not re.search(r"(Z|[+-]\d\d:\d\d)$", value):
        raise SemanticError(f"timezone required: {value}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SemanticError(f"invalid RFC3339 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SemanticError(f"timezone required: {value}")
    return parsed.astimezone(UTC)


def require_rfc3339(value: str) -> None:
    parse_rfc3339(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise SemanticError(f"{name} must be finite")


def candidate_set_id(candidates: list[dict[str, Any]]) -> str:
    """Order-independent ID; identity changes cannot silently retain the set ID."""
    fields = (
        "candidate_id",
        "issuer_id",
        "issuer_name",
        "ticker",
        "exchange",
        "share_class",
        "is_adr",
        "underlying_security_id",
        "listing_country",
    )
    identities = []
    for candidate in candidates:
        identity = {field: candidate[field] for field in fields}
        identity["former_tickers"] = sorted(candidate["former_tickers"])
        identity["corporate_action_lineage"] = sorted(candidate["corporate_action_lineage"])
        identities.append(identity)
    identities.sort(key=canonical_hash)
    return "cs_" + canonical_hash(identities)[:24]
