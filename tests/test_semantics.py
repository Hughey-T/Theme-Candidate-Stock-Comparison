from __future__ import annotations

import copy
import math

import pytest

from theme_compare.engine import classify, derive_scenario_results, update_diff
from theme_compare.models import SemanticError
from theme_compare.validation import validate_candidates, validate_envelope, validate_scores


def test_candidates_valid(candidates):
    validate_candidates(*candidates)


@pytest.mark.parametrize("mutation", ["id", "identity", "former", "set"])
def test_candidate_mutations_rejected(candidates, mutation):
    rows, set_id = copy.deepcopy(candidates)
    if mutation == "id":
        rows[1]["candidate_id"] = rows[0]["candidate_id"]
    elif mutation == "identity":
        for key in ("issuer_id", "ticker", "exchange", "share_class", "is_adr"):
            rows[1][key] = rows[0][key]
    elif mutation == "former":
        rows[1]["former_tickers"] = [rows[0]["ticker"]]
    else:
        set_id = "tampered"
    with pytest.raises(SemanticError):
        validate_candidates(rows, set_id)


def scenario_input():
    base = {
        "current_price": 100.0,
        "target_price": 110.0,
        "diluted_shares": 10.0,
        "dividend": 1.0,
        "permanent_loss": False,
        "realization_months": 12,
        "market_demand": 1.0,
        "company_share": 0.1,
        "revenue": 10.0,
        "margin": 0.2,
        "free_cash_flow": 1.0,
        "capex": 0.5,
        "valuation_multiple": 10.0,
        "assumptions": ["x"],
        "failure_conditions": ["y"],
    }
    return {
        "AAA": {
            name: {**base, "target_price": target, "permanent_loss": name == "THEME_BEAR"}
            for name, target in zip(
                ("THEME_BEAR", "THEME_BASE", "THEME_BULL"), (50.0, 110.0, 160.0)
            )
        }
        | {
            "expected_time_to_realization": 1.0,
            "upside_downside_asymmetry": 1.2,
            "confidence": "medium",
        }
    }


def test_scenario_derivation_recalculates_expected_values():
    result = derive_scenario_results(
        {"THEME_BEAR": 0.2, "THEME_BASE": 0.5, "THEME_BULL": 0.3}, scenario_input()
    )
    assert result["AAA"]["probability_weighted_return"] == pytest.approx(0.14)
    assert result["AAA"]["permanent_loss_probability"] == 0.2


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nonfinite_probability_rejected(bad):
    with pytest.raises(SemanticError):
        derive_scenario_results(
            {"THEME_BEAR": bad, "THEME_BASE": 0.5, "THEME_BULL": 0.5}, scenario_input()
        )


def test_no_selection_is_first_class(judgments):
    result = classify(["AAA"], {"AAA": []}, {"AAA": 0.02}, 0.05, judgments)
    assert result["no_selection"] and result["classifications"][0]["classification"] == "WATCH"


def test_hard_gate_cannot_be_offset(judgments):
    result = classify(
        ["AAA", "BBB"],
        {"AAA": ["going_concern"], "BBB": []},
        {"AAA": 9.0, "BBB": 0.2},
        0.05,
        judgments,
    )
    assert result["classifications"][0]["classification"] == "EXCLUDED"
    assert result["classifications"][1]["classification"] == "PRIMARY"


@pytest.mark.parametrize(
    "state,comparability,weight",
    [
        ("observed", "not_comparable", 1),
        ("missing", "comparable", 1),
        ("stale", "comparable", 1),
        ("not_applicable", "comparable", 1),
    ],
)
def test_unusable_metric_cannot_score(state, comparability, weight):
    row = {
        "metrics": [
            {
                "state": state,
                "comparability": comparability,
                "weight": weight,
                "dependency_root": "pricing_power",
            }
        ]
    }
    with pytest.raises(SemanticError):
        validate_scores([row])


def test_dependency_double_counting_rejected():
    metrics = [
        {
            "state": "observed",
            "comparability": "comparable",
            "weight": 1,
            "dependency_root": "moat",
        },
        {
            "state": "observed",
            "comparability": "comparable",
            "weight": 1,
            "dependency_root": "moat",
        },
    ]
    with pytest.raises(SemanticError):
        validate_scores([{"metrics": metrics}])


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation_id", "g2"),
        ("candidate_set_id", "cs2"),
        ("source_cutoff_at", "2025-01-02T00:00:00Z"),
    ],
)
def test_mixed_envelope_rejected(field, value):
    envelope = {
        "generation_id": "g1",
        "candidate_set_id": "cs1",
        "comparison_as_of": "2025-01-01T00:00:00Z",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "artifacts": [
            {
                "generation_id": "g1",
                "candidate_set_id": "cs1",
                "source_cutoff_at": "2025-01-01T00:00:00Z",
            }
        ],
    }
    envelope["artifacts"][0][field] = value
    with pytest.raises(SemanticError):
        validate_envelope(envelope)


def test_timezone_and_future_rejected():
    with pytest.raises(SemanticError):
        validate_envelope(
            {
                "generation_id": "g",
                "candidate_set_id": "c",
                "comparison_as_of": "2025-01-01T00:00:00",
                "source_cutoff_at": "2025-01-01T00:00:00Z",
                "artifacts": [],
            }
        )


def test_update_diff_only_reports_changes():
    changes = update_diff(
        {"generation_id": "g1", "price": 1, "same": 2},
        {"generation_id": "g2", "price": 3, "same": 2},
    )
    assert changes == [{"field": "price", "before": 1, "after": 3, "change": "changed"}]
