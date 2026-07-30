"""Immutable, bounded, hash-addressed publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .constants import MAX_PART_BYTES, SCHEMA_VERSION
from .models import SemanticError, canonical_hash


def split_payload(
    payload: dict[str, Any], generation_id: str, limit: int = MAX_PART_BYTES
) -> list[bytes]:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    if limit <= 0 or limit > MAX_PART_BYTES:
        raise SemanticError("invalid part size")
    return [raw[offset : offset + limit] for offset in range(0, len(raw), limit)] or [b"{}"]


def publish(root: Path, payload: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    generation = context["generation_id"]
    directory = root / "generations" / generation
    if directory.exists():
        raise SemanticError("immutable generation already exists")
    directory.mkdir(parents=True)
    parts = split_payload(payload, generation)
    inventory = []
    for index, raw in enumerate(parts, 1):
        name = f"detail.part-{index:03d}.json"
        (directory / name).write_bytes(raw)
        inventory.append(
            {
                "path": name,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                "sequence": index,
                "part_count": len(parts),
                "generation_id": generation,
            }
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        **context,
        "inventory": inventory,
        "canonical_sha256": canonical_hash(payload),
        "verification_status": "generated_not_persisted",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (root / "latest").write_text(generation + "\n")
    return manifest


def reconstruct(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    inventory = manifest["inventory"]
    if [x["sequence"] for x in inventory] != list(range(1, len(inventory) + 1)):
        raise SemanticError("part order/duplicate/gap")
    raw = b""
    for item in inventory:
        if (
            item["part_count"] != len(inventory)
            or item["generation_id"] != manifest["generation_id"]
        ):
            raise SemanticError("part count or generation mismatch")
        part = (directory / item["path"]).read_bytes()
        if len(part) != item["size"] or hashlib.sha256(part).hexdigest() != item["raw_sha256"]:
            raise SemanticError("part hash/size mismatch")
        raw += part
    value: dict[str, Any] = json.loads(raw)
    if canonical_hash(value) != manifest["canonical_sha256"]:
        raise SemanticError("reconstruction hash mismatch")
    return value
