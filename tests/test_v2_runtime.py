from pathlib import Path

import pytest

from theme_compare.models import SemanticError
from theme_compare.storage import JsonVolumeStorage
from theme_compare.v2_runtime import V2RuntimeService


def candidate(candidate_id: str):
    return {
        "candidate_id": candidate_id,
        "issuer_id": f"issuer-{candidate_id}",
        "issuer_name": candidate_id,
        "ticker": candidate_id,
        "exchange": "XNAS",
        "share_class": "common",
        "is_adr": False,
        "underlying_security_id": None,
        "former_tickers": [],
        "corporate_action_lineage": [],
        "listing_country": "US",
    }


def create(service):
    return service.create(
        {
            "contract_version": "2.0.0",
            "mode": "pipeline",
            "theme": "AI",
            "analysis_as_of": "2026-01-02T00:00:00Z",
            "source_cutoff_at": "2026-01-01T00:00:00Z",
            "candidates": [candidate("B"), candidate("A")],
            "horizons": [
                {
                    "horizon_id": "medium",
                    "minimum_months": 6,
                    "maximum_months": 18,
                    "benchmark": "SPY",
                    "required_return": 0.1,
                }
            ],
            "blind_handoff": {},
            "reconciliation_handoff": {"upstream_integrated_rank": ["B", "A"]},
        }
    )


def artifact(phase, payload=None):
    return {"generation_id": "g1", "phase": phase, "information": [], "payload": payload or {}}


def test_blind_order_freeze_disclosure_and_twelve_phases(tmp_path: Path):
    service = V2RuntimeService(JsonVolumeStorage(tmp_path))
    created = create(service)
    sid = created["session_id"]
    assert created["candidate_order"] == ["A", "B"]
    with pytest.raises(SemanticError):
        service.disclose(sid)
    for phase in range(1, 10):
        payload = {}
        if phase == 2:
            payload = {"eligible_candidate_set": ["A", "B"]}
        if phase == 6:
            payload = {"deep_comparison_set": ["A", "B"]}
        service.submit(sid, artifact(phase, payload))
    ai = {"medium": [{"candidate_id": "A", "rank": 1}, {"candidate_id": "B", "rank": 2}]}
    service.submit(sid, artifact(10, {"independent_ai_ranking": ai}))
    assert "upstream_reconciliation" in service.disclose(sid)
    with pytest.raises(SemanticError):
        service.submit(
            sid,
            artifact(
                11,
                {
                    "independent_ai_ranking": {},
                    "rankings": {},
                    "deep_candidates": [],
                    "pairwise": [],
                },
            ),
        )
    rankings = {
        "evidence_only_mechanical": {"inputs": [{"classification": "FACTS"}]},
        "scenario_derived": {"inputs": [{"classification": "AI_ASSUMPTIONS"}]},
    }
    pair = {"candidate_a": "A", "candidate_b": "B"}
    service.submit(
        sid,
        artifact(
            11,
            {
                "independent_ai_ranking": ai,
                "rankings": rankings,
                "deep_candidates": ["A", "B"],
                "pairwise": [pair],
            },
        ),
    )
    final = {
        "integrated_selection": {
            "decision": "NO_SELECTION",
            "selected_candidates": [],
            "hard_gates": {"A": [], "B": []},
        },
        "decision_ledger": [],
        "reconciliation_handoff": {"decision": "NO_SELECTION"},
    }
    assert service.submit(sid, artifact(12, final))["status"] == "complete"
    assert service.handoff(sid, False)["candidates"] == []
    with pytest.raises(SemanticError):
        service.handoff(sid, True)
    service.acknowledge_blind(sid)
    assert service.handoff(sid, True)["decision"] == "NO_SELECTION"


def test_mechanical_purity_and_strictly_newer_update_cutoff(tmp_path: Path):
    service = V2RuntimeService(JsonVolumeStorage(tmp_path))
    sid = create(service)["session_id"]
    state = service._load(sid)
    state["status"] = "complete"
    service._write(sid, state)
    with pytest.raises(SemanticError):
        service.start_update(
            sid,
            {
                "new_generation_id": "g2",
                "analysis_as_of": "2026-01-02T00:00:00Z",
                "source_cutoff_at": "2025-12-31T19:00:00-05:00",
                "candidates": [candidate("A")],
            },
        )


def test_update_four_phases_archive_handoff_and_v1_v2_state_isolation(tmp_path: Path):
    storage = JsonVolumeStorage(tmp_path)
    service = V2RuntimeService(storage)
    sid = create(service)["session_id"]
    state = service._load(sid)
    state.update(
        status="complete",
        handoffs={"blind": {"generation": "g1"}, "reconciliation": {"generation": "g1"}},
        ledger=[{"generation": "g1"}],
    )
    service._write(sid, state)
    # The v2 suffix cannot be loaded through the validated legacy v1 state path.
    with pytest.raises(FileNotFoundError):
        storage.load(sid)

    started = service.start_update(
        sid,
        {
            "new_generation_id": "g2",
            "analysis_as_of": "2026-02-02T00:00:00Z",
            "source_cutoff_at": "2026-02-01T00:00:00Z",
            "candidates": [candidate("A"), candidate("B")],
        },
    )
    assert started["next_phase"] == 1
    assert service.submit(sid, {**artifact(1), "generation_id": "g2"})["next_phase"] == 2
    ai = {"medium": [{"candidate_id": "B", "rank": 1}, {"candidate_id": "A", "rank": 2}]}
    service.submit(
        sid,
        {**artifact(2, {"independent_ai_ranking": ai}), "generation_id": "g2"},
    )
    rankings = {
        "evidence_only_mechanical": {"inputs": [{"classification": "FACTS"}]},
        "scenario_derived": {"inputs": [{"classification": "AI_ASSUMPTIONS"}]},
    }
    service.submit(
        sid,
        {
            **artifact(
                3,
                {
                    "independent_ai_ranking": ai,
                    "rankings": rankings,
                    "deep_candidates": ["A", "B"],
                    "pairwise": [{"candidate_a": "A", "candidate_b": "B"}],
                    # A cycle is retained as an explicit artifact, not forced into a score.
                    "condorcet_cycles": [["A", "B", "A"]],
                    "sensitivity": [{"candidate_id": "A", "robust_rank_range": [1, 2]}],
                },
            ),
            "generation_id": "g2",
        },
    )
    final = {
        "integrated_selection": {
            "decision": "SELECTION",
            "selected_candidates": ["B"],
            "hard_gates": {"A": [], "B": []},
        },
        "decision_ledger": [{"candidate_id": "B", "generation_id": "g2"}],
        "reconciliation_handoff": {"generation": "g2"},
    }
    result = service.submit(sid, {**artifact(4, final), "generation_id": "g2"})
    assert result["status"] == "complete"
    persisted = service._load(sid)
    assert persisted["generation_history"][0]["handoffs"]["blind"] == {"generation": "g1"}
    assert persisted["ledger"] == [{"candidate_id": "B", "generation_id": "g2"}]
