import pytest

from theme_compare.models import SemanticError
from theme_compare.publication import publish, reconstruct, split_payload


def context():
    return {
        "generation_id": "g1",
        "candidate_set_id": "cs1",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "created_at": "2025-01-01T01:00:00Z",
    }


def test_split_publish_reconstruct(tmp_path):
    payload = {"value": "x" * 1000}
    manifest = publish(tmp_path, payload, context())
    assert len(manifest["inventory"]) == 1
    assert reconstruct(tmp_path / "generations/g1", manifest) == payload


@pytest.mark.parametrize("mutation", ["hash", "order", "count", "generation", "missing"])
def test_publication_mutations(tmp_path, mutation):
    manifest = publish(tmp_path, {"value": "x" * 100}, context())
    item = manifest["inventory"][0]
    if mutation == "hash":
        item["raw_sha256"] = "0" * 64
    elif mutation == "order":
        item["sequence"] = 2
    elif mutation == "count":
        item["part_count"] = 2
    elif mutation == "generation":
        item["generation_id"] = "g2"
    else:
        (tmp_path / "generations/g1" / item["path"]).unlink()
    with pytest.raises((SemanticError, FileNotFoundError)):
        reconstruct(tmp_path / "generations/g1", manifest)


def test_oversized_requested_part_rejected():
    with pytest.raises(SemanticError):
        split_payload({"x": 1}, "g", 999999)


def test_generation_is_immutable(tmp_path):
    publish(tmp_path, {"x": 1}, context())
    with pytest.raises(SemanticError):
        publish(tmp_path, {"x": 2}, context())
