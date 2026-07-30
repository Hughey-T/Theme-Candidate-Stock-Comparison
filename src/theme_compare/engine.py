"""Scenario derivation, selection, update diff and handoff construction."""

from __future__ import annotations

from typing import Any

from .constants import CLASSIFICATIONS, SCENARIOS, SCHEMA_VERSION
from .models import SemanticError
from .validation import validate_scenarios, validate_selection


def derive_scenario_results(common: dict[str, float], inputs: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for candidate_id, candidate in inputs.items():
        expected = downside = loss = 0.0
        cases: dict[str, Any] = {}
        for scenario in SCENARIOS:
            case = dict(candidate[scenario])
            case["total_return"] = (case["target_price"] + case["dividend"]) / case[
                "current_price"
            ] - 1
            probability = common[scenario]
            expected += probability * case["total_return"]
            downside += probability if case["total_return"] < 0 else 0
            loss += probability if case["permanent_loss"] else 0
            cases[scenario] = case
        output[candidate_id] = {
            "scenarios": cases,
            "probability_weighted_return": expected,
            "downside_probability": downside,
            "permanent_loss_probability": loss,
            "expected_time_to_realization": candidate["expected_time_to_realization"],
            "upside_downside_asymmetry": candidate["upside_downside_asymmetry"],
            "confidence": candidate["confidence"],
        }
    validate_scenarios(common, output)
    return output


def classify(
    ranking: list[str],
    hard_gates: dict[str, list[str]],
    expected: dict[str, float],
    benchmark_return: float,
    judgments: list[dict[str, Any]],
) -> dict[str, Any]:
    excluded = {candidate for candidate, gates in hard_gates.items() if gates}
    eligible = [candidate for candidate in ranking if candidate not in excluded]
    attractive = bool(eligible and expected[eligible[0]] > benchmark_return)
    classifications = []
    selected_index = 0
    for candidate in ranking:
        if candidate in excluded:
            label = "EXCLUDED"
        elif not attractive:
            label = "WATCH"
        elif selected_index == 0:
            label = "PRIMARY"
            selected_index += 1
        elif selected_index == 1 and expected[candidate] > benchmark_return:
            label = "SECONDARY"
            selected_index += 1
        elif expected[candidate] > 0:
            label = "CONDITIONAL"
        else:
            label = "WATCH"
        classifications.append({"candidate_id": candidate, "classification": label})
    payload = {
        "ranking": ranking,
        "hard_gates": hard_gates,
        "classifications": classifications,
        "absolute_attractiveness": attractive,
        "no_selection": not attractive,
        "judgments": judgments,
    }
    validate_selection(payload)
    return payload


def update_diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    if old["generation_id"] == new["generation_id"]:
        raise SemanticError("update must create a generation")
    keys = sorted((set(old) | set(new)) - {"generation_id"})
    return [
        {"field": key, "before": old.get(key), "after": new.get(key), "change": "changed"}
        for key in keys
        if old.get(key) != new.get(key)
    ]


def build_handoff(context: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    by_class: dict[str, list[str]] = {name: [] for name in CLASSIFICATIONS}
    for row in selection["classifications"]:
        by_class[row["classification"]].append(row["candidate_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        **{
            key: context[key]
            for key in (
                "session_id",
                "generation_id",
                "candidate_set_id",
                "theme",
                "comparison_as_of",
                "source_cutoff_at",
                "ranking_by_horizon",
                "common_scenarios",
                "company_scenario_results",
                "key_assumptions",
                "shared_theme_risks",
                "company_specific_risks",
                "catalysts",
                "valuation_ranges",
                "thesis_invalidation_conditions",
                "confidence",
                "evidence_manifest",
            )
        },
        "investment_horizon": {"tactical": "6-12 months", "structural": "2-3 years"},
        "primary_candidate": by_class["PRIMARY"][0] if by_class["PRIMARY"] else None,
        "secondary_candidate": by_class["SECONDARY"][0] if by_class["SECONDARY"] else None,
        "conditional_candidates": by_class["CONDITIONAL"],
        "watch_candidates": by_class["WATCH"],
        "excluded_candidates": by_class["EXCLUDED"],
        "no_selection": selection["no_selection"],
        "recommended_next_action": "個別株完全分析"
        if not selection["no_selection"]
        else "NO_SELECTION",
    }
