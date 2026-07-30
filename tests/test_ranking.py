from __future__ import annotations

import copy

import pytest

from theme_compare.models import SemanticError
from theme_compare.ranking import RANKING_TYPES, derive_rankings, validate_stored_rankings


def metrics() -> list[dict[str, object]]:
    return [
        {
            "candidate_id": candidate,
            "ranking_type": ranking_type,
            "value": value,
            "weight": 1.0,
            "effective_weight": 1.0,
            "applicable": True,
            "state": "observed",
            "comparability": "comparable",
            "dependency_root": f"{ranking_type}-root",
        }
        for candidate, value in (("A", 0.8), ("B", 0.6))
        for ranking_type in RANKING_TYPES
    ]


def test_derives_five_rankings_and_scores():
    rankings, scores = derive_rankings(["A", "B"], metrics())
    assert set(rankings) == set(RANKING_TYPES)
    assert all(order == ["A", "B"] for order in rankings.values())
    assert scores["tactical"] == {"A": 0.8, "B": 0.6}


def test_deterministic_candidate_id_tie_break():
    rows = metrics()
    for row in rows:
        row["value"] = 0.5
    rankings, _ = derive_rankings(["B", "A"], rows)
    assert rankings["risk_adjusted"] == ["A", "B"]


@pytest.mark.parametrize("mutation", ["ranking", "score"])
def test_stored_ranking_or_score_mutation_rejected(mutation):
    rankings, scores = derive_rankings(["A", "B"], metrics())
    stored = {"ordered_candidates": copy.deepcopy(rankings), "scores": copy.deepcopy(scores)}
    if mutation == "ranking":
        stored["ordered_candidates"]["tactical"].reverse()
    else:
        stored["scores"]["tactical"]["A"] = 0.1
    with pytest.raises(SemanticError, match="stored ranking"):
        validate_stored_rankings(["A", "B"], metrics(), stored, set())


def test_excluded_removed_and_unusable_metric_not_weighted():
    rows = metrics()
    row = next(
        item for item in rows if item["candidate_id"] == "A" and item["ranking_type"] == "tactical"
    )
    row.update(state="missing", effective_weight=0.0)
    with pytest.raises(SemanticError, match="eligible metric weight"):
        derive_rankings(["A", "B"], rows, {"B"})
