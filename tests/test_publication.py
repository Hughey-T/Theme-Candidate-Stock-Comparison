import copy
import json
import pytest
from theme_compare.models import SemanticError
from theme_compare.publication import (
    publish,
    reconstruct,
    split_payload,
    transition_persistence,
    terminal_failure,
    update_latest,
)


def context():
    return {
        "generation_id": "g1",
        "candidate_set_id": "cs1",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "created_at": "2025-01-01T01:00:00Z",
    }


def test_utf8_safe_atomic_publish_reconstruct(tmp_path):
    payload = {"value": "株式🚀" * 20000}
    manifest = publish(tmp_path, payload, context())
    assert (
        len(manifest["inventory"]) > 1
        and reconstruct(tmp_path / "generations/g1", manifest) == payload
    )
    assert not (tmp_path / "latest").exists()
    for item in manifest["inventory"]:
        __import__("json").loads((tmp_path / "generations/g1" / item["path"]).read_text())


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "order",
        "count",
        "generation",
        "missing",
        "duplicate_path",
        "duplicate_sequence",
        "traversal",
    ],
)
def test_publication_mutations(tmp_path, mutation):
    manifest = publish(tmp_path, {"value": "x" * 100}, context())
    item = manifest["inventory"][0]
    directory = tmp_path / "generations/g1"
    if mutation == "hash":
        item["raw_sha256"] = "0" * 64
    elif mutation == "order":
        item["sequence"] = 2
    elif mutation == "count":
        item["part_count"] = 2
    elif mutation == "generation":
        item["generation_id"] = "g2"
    elif mutation == "missing":
        (directory / item["path"]).unlink()
    elif mutation == "duplicate_path":
        manifest["inventory"].append(copy.deepcopy(item))
    elif mutation == "duplicate_sequence":
        duplicate = copy.deepcopy(item)
        duplicate["path"] = "other.json"
        manifest["inventory"].append(duplicate)
    elif mutation == "traversal":
        item["path"] = "../outside.json"
    with pytest.raises((SemanticError, FileNotFoundError)):
        reconstruct(directory, manifest)


def test_unknown_file_and_symlink_rejected(tmp_path):
    manifest = publish(tmp_path, {"x": 1}, context())
    directory = tmp_path / "generations/g1"
    (directory / "unknown").write_text("x")
    with pytest.raises(SemanticError, match="inventory"):
        reconstruct(directory, manifest)


@pytest.mark.parametrize(
    "mutation", ["missing_manifest", "modified_manifest", "inventory_removed", "schema_invalid"]
)
def test_manifest_is_loaded_and_verified_from_disk(tmp_path, mutation):
    manifest = publish(tmp_path, {"x": 1}, context())
    directory = tmp_path / "generations/g1"
    path = directory / "manifest.json"
    if mutation == "missing_manifest":
        path.unlink()
    elif mutation == "modified_manifest":
        value = json.loads(path.read_text())
        value["canonical_sha256"] = "0" * 64
        path.write_text(json.dumps(value))
    elif mutation == "inventory_removed":
        value = json.loads(path.read_text())
        value["inventory"] = []
        path.write_text(json.dumps(value))
    else:
        value = json.loads(path.read_text())
        value["unknown"] = True
        path.write_text(json.dumps(value))
    with pytest.raises(SemanticError):
        reconstruct(directory, manifest)


def test_oversized_requested_part_rejected():
    with pytest.raises(SemanticError):
        split_payload({"x": 1}, "g", 999999)


def test_generation_is_immutable(tmp_path):
    publish(tmp_path, {"x": 1}, context())
    with pytest.raises(SemanticError):
        publish(tmp_path, {"x": 2}, context())


def test_failed_publication_is_removed_and_retryable(tmp_path, monkeypatch):
    import theme_compare.publication as module

    original = module.reconstruct
    monkeypatch.setattr(
        module, "reconstruct", lambda *_: (_ for _ in ()).throw(SemanticError("boom"))
    )
    with pytest.raises(SemanticError):
        publish(tmp_path, {"x": 1}, context())
    assert not (tmp_path / "generations/g1").exists()
    monkeypatch.setattr(module, "reconstruct", original)
    publish(tmp_path, {"x": 1}, context())


def test_persistence_lifecycle_and_latest(tmp_path):
    status = "not_generated"
    for target in (
        "generated_not_persisted",
        "persisted_pending_verification",
        "integrity_verified",
    ):
        status = transition_persistence(status, target)
    manifest = {**context(), "verification_status": status}
    update_latest(tmp_path, manifest)
    assert (tmp_path / "latest").read_text().strip() == "g1"
    with pytest.raises(SemanticError):
        transition_persistence(status, status)
    with pytest.raises(SemanticError):
        update_latest(tmp_path, {**manifest, "verification_status": "generated_not_persisted"})


def test_terminal_failure_requires_metadata_and_cannot_recover():
    record = terminal_failure(
        "generated_not_persisted", "hash mismatch", "2025-01-01T00:00:00Z", "remote_verify"
    )
    assert record["verification_status"] == "failed_terminal"
    with pytest.raises(SemanticError):
        transition_persistence("failed_terminal", "not_generated")
    with pytest.raises(SemanticError):
        transition_persistence(
            "integrity_verified",
            "failed_terminal",
            failure_reason="x",
            failed_at="2025-01-01T00:00:00Z",
            failed_stage="x",
        )
    with pytest.raises(SemanticError):
        transition_persistence("not_generated", "failed_terminal")
