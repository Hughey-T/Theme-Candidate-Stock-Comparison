from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import pytest
from phase_fixtures import artifact
from test_runtime import runtime_artifact, service, upstream
from theme_compare.models import SemanticError
from theme_compare.storage import JsonVolumeStorage, StorageError


@pytest.mark.parametrize("session_id", ["../x", "s_bad", "s_" + "a" * 31, "s_" + "g" * 32])
def test_path_traversal_and_invalid_id(tmp_path, session_id):
    with pytest.raises(SemanticError):
        JsonVolumeStorage(tmp_path).path(session_id)


def test_create_collision_corruption_and_restart(tmp_path):
    runtime = service(tmp_path)
    created = runtime.create(upstream())
    sid = created["session_id"]
    assert service(tmp_path).summary(sid)["active_generation_id"] == "g1"
    runtime.storage.path(sid).write_text('{"broken":')
    with pytest.raises(StorageError):
        runtime.summary(sid)


def test_concurrent_submission_only_one_wins(tmp_path):
    runtime = service(tmp_path)
    sid = runtime.create(upstream())["session_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(runtime.submit, sid, runtime_artifact(1)) for _ in range(2)]
    assert sum(f.exception() is None for f in futures) == 1
    assert runtime.summary(sid)["completed_phases"] == [1]


def test_validation_failure_is_byte_for_byte_unchanged_and_temp_clean(tmp_path):
    runtime = service(tmp_path)
    sid = runtime.create(upstream())["session_id"]
    before = runtime.storage.path(sid).read_bytes()
    bad = artifact(2)
    with pytest.raises(SemanticError):
        runtime.submit(sid, bad)
    assert runtime.storage.path(sid).read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_health_missing_root(tmp_path):
    root = tmp_path / "missing"
    storage = JsonVolumeStorage(root, create_root=False)
    assert storage.health() is False
