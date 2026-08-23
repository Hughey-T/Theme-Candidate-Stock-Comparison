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


def artifact(phase: int, payload=None):
    return {"generation_id": "g1", "phase": phase, "information": [], "payload": payload or {}}


def create(service: V2RuntimeService) -> str:
    result = service.create(
        {
            "contract_version": "2.0.0",
            "mode": "standalone",
            "theme": "AI infrastructure",
            "analysis_as_of": "2026-08-22T00:00:00Z",
            "source_cutoff_at": "2026-08-21T23:59:59Z",
            "candidates": [candidate("A"), candidate("B")],
            "horizons": [
                {
                    "horizon_id": "medium",
                    "minimum_months": 12,
                    "maximum_months": 24,
                    "benchmark": "SPY",
                    "required_return": 0.1,
                }
            ],
        }
    )
    return result["session_id"]


def advance_to_phase(service: V2RuntimeService, sid: str, target: int) -> None:
    while service.contract(sid)["phase"] < target:
        phase = service.contract(sid)["phase"]
        payload = {}
        if phase == 2:
            payload = {"eligible_candidate_set": ["A", "B"]}
        if phase == 6:
            payload = {"deep_comparison_set": ["A", "B"]}
        if phase == 10:
            payload = {
                "independent_ai_ranking": {
                    "medium": [
                        {"candidate_id": "A", "rank": 1},
                        {"candidate_id": "B", "rank": 2},
                    ]
                }
            }
        service.submit(sid, artifact(phase, payload))


def test_contract_exposes_transition_and_cutoff_requirements(tmp_path: Path) -> None:
    service = V2RuntimeService(JsonVolumeStorage(tmp_path))
    sid = create(service)
    service.submit(sid, artifact(1))

    phase2 = service.contract(sid)
    assert phase2["source_cutoff_at"] == "2026-08-21T23:59:59Z"
    requirements = phase2["submission_requirements"]
    assert requirements["evidence_as_of_max"] == phase2["source_cutoff_at"]
    assert requirements["required_payload_keys"] == ["eligible_candidate_set"]
    assert requirements["candidate_transition"] == {
        "field": "eligible_candidate_set",
        "max_candidates": 8,
        "allowed_candidate_ids": ["A", "B"],
    }

    service.submit(sid, artifact(2, {"eligible_candidate_set": ["A", "B"]}))
    advance_to_phase(service, sid, 6)
    phase6 = service.contract(sid)["submission_requirements"]
    assert phase6["required_payload_keys"] == ["deep_comparison_set"]
    assert phase6["candidate_transition"]["max_candidates"] == 5


def test_reconciliation_can_omit_frozen_ranking_but_cannot_change_it(tmp_path: Path) -> None:
    service = V2RuntimeService(JsonVolumeStorage(tmp_path))
    sid = create(service)
    advance_to_phase(service, sid, 11)

    requirements = service.contract(sid)["submission_requirements"]
    assert requirements["required_payload_keys"] == ["rankings", "deep_candidates", "pairwise"]
    assert requirements["independent_ai_ranking_policy"].startswith("omit;")
    rankings = {
        "evidence_only_mechanical": {"inputs": [{"classification": "FACTS"}]},
        "scenario_derived": {"inputs": [{"classification": "AI_ASSUMPTIONS"}]},
    }
    reconciliation = {
        "rankings": rankings,
        "deep_candidates": ["A", "B"],
        "pairwise": [{"candidate_a": "A", "candidate_b": "B"}],
    }
    result = service.submit(sid, artifact(11, reconciliation))
    assert result["accepted"] is True
    assert result["next_phase"] == 12

    service2 = V2RuntimeService(JsonVolumeStorage(tmp_path / "other"))
    sid2 = create(service2)
    advance_to_phase(service2, sid2, 11)
    with pytest.raises(SemanticError, match="independent AI ranking is immutable"):
        service2.submit(
            sid2,
            artifact(
                11,
                {
                    **reconciliation,
                    "independent_ai_ranking": {"medium": []},
                },
            ),
        )
