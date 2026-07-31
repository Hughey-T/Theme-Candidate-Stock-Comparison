from __future__ import annotations
import copy
import json
import pytest
from phase_fixtures import CANDIDATE, CANDIDATE_B, artifact
from theme_compare.models import SemanticError, candidate_set_id
from theme_compare.runtime import RuntimeService, phase_schema
from theme_compare.storage import JsonVolumeStorage


def upstream(candidates=None):
    return {
        "schema_version": "1.0.0",
        "theme": "AI",
        "hypothesis": "growth",
        "comparison_as_of": "2025-01-01T00:00:00Z",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "candidate_inputs": copy.deepcopy(
            candidates if candidates is not None else [CANDIDATE, CANDIDATE_B]
        ),
        "source_generation_id": "source-g1",
        "source_session_id": "source-s1",
        "evidence_refs": ["SOURCE-E1"],
    }


def service(tmp_path):
    return RuntimeService(JsonVolumeStorage(tmp_path))


def runtime_artifact(phase, *args):
    item = artifact(phase, *args)
    if phase == 1 and (not args or len(args) < 2 or args[1] == "initial"):
        payload = item["payload"]["session_and_candidates"]
        payload.update(
            source_session_id="source-s1",
            source_generation_id="source-g1",
            upstream_evidence_refs=["SOURCE-E1"],
        )
    return item


def test_artifact_and_upstream_candidate_graphs_are_isolated():
    original_set_id = candidate_set_id([CANDIDATE, CANDIDATE_B])
    first = artifact(1)
    second = artifact(1)
    first_payload = first["payload"]["session_and_candidates"]
    first_payload["candidate_inputs"][0]["ticker"] = "OTHER"
    first_payload["normalized_candidates"].reverse()
    first_payload["candidate_inputs"][0]["former_tickers"].append("OLD")
    assert second["payload"]["session_and_candidates"]["candidate_inputs"][0]["ticker"] == "AAA"
    assert (
        second["payload"]["session_and_candidates"]["normalized_candidates"][0]["candidate_id"]
        == "A"
    )
    assert CANDIDATE["ticker"] == "AAA" and CANDIDATE["former_tickers"] == []
    assert candidate_set_id([CANDIDATE, CANDIDATE_B]) == original_set_id
    first_upstream = upstream()
    second_upstream = upstream()
    first_upstream["candidate_inputs"][0]["ticker"] = "CHANGED"
    assert second_upstream["candidate_inputs"][0]["ticker"] == "AAA"
    assert CANDIDATE["ticker"] == "AAA"


def test_upstream_is_authoritative_and_phase_schema_is_single_branch(tmp_path):
    runtime = service(tmp_path)
    created = runtime.create(upstream())
    contract = created["next_contract"]
    assert created["upstream_candidate_set_id"] == candidate_set_id([CANDIDATE, CANDIDATE_B])
    assert contract["source_lineage"]["source_session_id"] == "source-s1"
    assert "oneOf" not in contract["artifact_schema"]
    assert contract["artifact_schema"]["properties"]["mode"] == {"const": "initial"}
    assert len(json.dumps(contract["artifact_schema"])) < len(
        json.dumps(
            json.loads(
                __import__("theme_compare.schema_runtime", fromlist=["schema_bytes"]).schema_bytes(
                    "phase-artifact"
                )
            )
        )
    )


def test_initial_bootstrap_order_independent_and_mismatch_does_not_mutate(tmp_path):
    runtime = service(tmp_path)
    sid = runtime.create(upstream())["session_id"]
    item = runtime_artifact(1)
    item["payload"]["session_and_candidates"]["candidate_inputs"].reverse()
    item["payload"]["session_and_candidates"]["normalized_candidates"].reverse()
    runtime.submit(sid, item)
    assert runtime.summary(sid)["completed_phases"] == [1]
    sid2 = runtime.create(upstream())["session_id"]
    bad = runtime_artifact(1)
    bad["payload"]["session_and_candidates"]["theme"] = "changed"
    before = runtime.storage.path(sid2).read_bytes()
    with pytest.raises(SemanticError):
        runtime.submit(sid2, bad)
    assert runtime.storage.path(sid2).read_bytes() == before


def test_twelve_to_eight_candidate_lifecycle(tmp_path):
    candidates = []
    for i in range(12):
        row = {
            **CANDIDATE,
            "candidate_id": f"C{i}",
            "issuer_id": f"issuer-{i}",
            "issuer_name": f"Issuer {i}",
            "ticker": f"T{i}",
        }
        candidates.append(row)
    runtime = service(tmp_path)
    sid = runtime.create(upstream(candidates))["session_id"]
    item = runtime_artifact(1)
    payload = item["payload"]["session_and_candidates"]
    payload["candidate_inputs"] = list(reversed(candidates))
    payload["normalized_candidates"] = candidates[:8]
    payload["exclusions"] = [
        {"candidate_id": x["candidate_id"], "reason": "limit"} for x in candidates[8:]
    ]
    analysis = candidate_set_id(candidates[:8])
    payload["candidate_set_id"] = analysis
    item["candidate_set_id"] = analysis
    runtime.submit(sid, item)
    summary = runtime.summary(sid)
    assert (
        summary["analysis_candidate_set_id"] == analysis and summary["candidate_set_id"] == analysis
    )


def test_exclusion_and_identity_mismatch_rejected(tmp_path):
    runtime = service(tmp_path)
    sid = runtime.create(upstream())["session_id"]
    for mutate in (
        lambda p: p["exclusions"].append({"candidate_id": "B", "reason": "wrong"}),
        lambda p: p["candidate_inputs"][0].update(ticker="OTHER"),
    ):
        bad = runtime_artifact(1)
        mutate(bad["payload"]["session_and_candidates"])
        with pytest.raises(SemanticError):
            runtime.submit(sid, bad)


def test_phase_schema_all_modes():
    for mode, maximum in (("initial", 10), ("update", 2)):
        for phase in range(1, maximum + 1):
            schema = phase_schema(mode, phase)
            assert schema["additionalProperties"] is False
            assert (
                schema["properties"]["mode"]["const"] == mode
                and schema["properties"]["phase"]["const"] == phase
            )


def test_full_initial_two_updates_restart_and_handoff_history(tmp_path):
    runtime = service(tmp_path)
    sid = runtime.create(upstream())["session_id"]
    for phase in range(1, 11):
        runtime.submit(sid, runtime_artifact(phase))
    assert runtime.summary(sid)["status"] == "complete"
    assert runtime.handoff(sid)["active_handoff"]["handoff_id"] == "h1"
    runtime.update(
        sid,
        {
            "new_comparison_as_of": "2025-02-01T00:00:00Z",
            "new_source_cutoff_at": "2025-01-31T00:00:00Z",
            "candidate_inputs": [CANDIDATE_B, CANDIDATE],
        },
    )
    restarted = service(tmp_path)
    contract = restarted.contract(sid)
    assert contract["bootstrap"]["new_candidate_inputs"] == [CANDIDATE_B, CANDIDATE]
    restarted.submit(sid, artifact(1, "g2", "update", "2025-01-31T00:00:00Z"))
    restarted.submit(sid, artifact(2, "g2", "update", "2025-01-31T00:00:00Z"))
    restarted.update(
        sid,
        {
            "new_comparison_as_of": "2025-03-01T00:00:00Z",
            "new_source_cutoff_at": "2025-02-28T00:00:00Z",
            "candidate_inputs": [CANDIDATE, CANDIDATE_B],
        },
    )
    restarted.submit(sid, artifact(1, "g3", "update", "2025-02-28T00:00:00Z"))
    restarted.submit(sid, artifact(2, "g3", "update", "2025-02-28T00:00:00Z"))
    state = restarted.storage.load(sid)
    assert set(state["runtime_context"]["generation_contexts"]) == {"g1", "g2", "g3"}
    assert len(restarted.handoff(sid, True)["handoff_history"]) == 3
