"""Atomic, bounded, hash-addressed publication and explicit persistence lifecycle."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from .constants import MAX_PART_BYTES, PERSISTENCE, SCHEMA_VERSION
from .models import SemanticError, canonical_bytes, canonical_hash, parse_rfc3339
from .schema_runtime import validate_document


def transition_persistence(
    current: str,
    target: str,
    *,
    failure_reason: str | None = None,
    failed_at: str | None = None,
    failed_stage: str | None = None,
) -> str:
    if current == "failed_terminal":
        raise SemanticError("failed_terminal cannot transition")
    if target == "failed_terminal":
        if current == "integrity_verified" or not all((failure_reason, failed_at, failed_stage)):
            raise SemanticError("invalid terminal failure transition")
        parse_rfc3339(failed_at or "")
        return target
    path = PERSISTENCE[:4]
    if current not in path or target not in path or path.index(target) != path.index(current) + 1:
        raise SemanticError("invalid persistence transition")
    return target


def terminal_failure(current: str, reason: str, failed_at: str, stage: str) -> dict[str, str]:
    status = transition_persistence(
        current, "failed_terminal", failure_reason=reason, failed_at=failed_at, failed_stage=stage
    )
    return {
        "verification_status": status,
        "failure_reason": reason,
        "failed_at": failed_at,
        "failed_stage": stage,
    }


def split_payload(
    payload: dict[str, Any], generation_id: str, limit: int = MAX_PART_BYTES
) -> list[dict[str, Any]]:
    """Return standalone closed JSON part documents using base64-safe chunks."""
    if limit <= 256 or limit > MAX_PART_BYTES:
        raise SemanticError("invalid part size")
    raw = canonical_bytes(payload)
    # Base64 expands by 4/3; reserve space for the closed envelope.
    chunk_size = max(1, (limit - 256) * 3 // 4)
    chunks = [raw[offset : offset + chunk_size] for offset in range(0, len(raw), chunk_size)] or [
        b"{}"
    ]
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "generation_id": generation_id,
            "sequence": index,
            "part_count": len(chunks),
            "encoding": "base64",
            "data": base64.b64encode(chunk).decode("ascii"),
        }
        for index, chunk in enumerate(chunks, 1)
    ]


def publish(root: Path, payload: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    generation = context["generation_id"]
    generations = root / "generations"
    target = generations / generation
    if target.exists():
        raise SemanticError("immutable generation already exists")
    generations.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{generation}-", dir=generations))
    try:
        parts = split_payload(payload, generation)
        inventory = []
        for part in parts:
            name = f"detail.part-{part['sequence']:03d}.json"
            raw = canonical_bytes(part)
            if len(raw) > MAX_PART_BYTES:
                raise SemanticError("part exceeds byte limit")
            (temporary / name).write_bytes(raw)
            inventory.append(
                {
                    "path": name,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "size": len(raw),
                    "sequence": part["sequence"],
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
        (temporary / "manifest.json").write_bytes(canonical_bytes(manifest))
        if reconstruct(temporary, manifest) != payload:
            raise SemanticError("publication verification failed")
        os.replace(temporary, target)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def reconstruct(directory: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SemanticError("manifest missing or symlinked")
    disk_bytes = manifest_path.read_bytes()
    disk_manifest = json.loads(disk_bytes)
    validate_document("publication-manifest", disk_manifest)
    if disk_bytes != canonical_bytes(manifest) or disk_manifest != manifest:
        raise SemanticError("on-disk manifest mismatch")
    if (
        not directory.name.startswith(f".{manifest['generation_id']}-")
        and directory.name != manifest["generation_id"]
    ):
        raise SemanticError("manifest/directory generation mismatch")
    inventory = manifest["inventory"]
    paths = [item["path"] for item in inventory]
    sequences = [item["sequence"] for item in inventory]
    if len(paths) != len(set(paths)) or len(sequences) != len(set(sequences)):
        raise SemanticError("duplicate path or sequence")
    if sequences != list(range(1, len(inventory) + 1)):
        raise SemanticError("part order/gap")
    expected_files = set(paths) | {"manifest.json"}
    actual_files = {entry.name for entry in directory.iterdir()}
    if actual_files != expected_files:
        raise SemanticError("generation inventory does not exactly match files")
    chunks = []
    for item in inventory:
        pure = PurePosixPath(item["path"])
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1:
            raise SemanticError("unsafe inventory path")
        path = directory / item["path"]
        if path.is_symlink() or not path.is_file():
            raise SemanticError("part missing or symlinked")
        if (
            item["part_count"] != len(inventory)
            or item["generation_id"] != manifest["generation_id"]
        ):
            raise SemanticError("part count or generation mismatch")
        raw = path.read_bytes()
        if len(raw) != item["size"] or hashlib.sha256(raw).hexdigest() != item["raw_sha256"]:
            raise SemanticError("part hash/size mismatch")
        part = json.loads(raw)
        if set(part) != {
            "schema_version",
            "generation_id",
            "sequence",
            "part_count",
            "encoding",
            "data",
        }:
            raise SemanticError("part document is not closed")
        if (
            part["generation_id"] != manifest["generation_id"]
            or part["sequence"] != item["sequence"]
            or part["part_count"] != len(inventory)
        ):
            raise SemanticError("part envelope mismatch")
        chunks.append(base64.b64decode(part["data"], validate=True))
    value: dict[str, Any] = json.loads(b"".join(chunks))
    if canonical_hash(value) != manifest["canonical_sha256"]:
        raise SemanticError("reconstruction hash mismatch")
    return value


def update_latest(root: Path, manifest: dict[str, Any]) -> None:
    if manifest["verification_status"] != "integrity_verified":
        raise SemanticError("latest requires remotely integrity-verified generation")
    temporary = root / ".latest.tmp"
    temporary.write_text(manifest["generation_id"] + "\n")
    os.replace(temporary, root / "latest")
