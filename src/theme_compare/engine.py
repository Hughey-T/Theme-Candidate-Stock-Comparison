"""Scenario derivation, selection, update diff and handoff construction."""

from __future__ import annotations

from typing import Any

from .constants import CLASSIFICATIONS, SCENARIOS, SCHEMA_VERSION
from .models import SemanticError, canonical_hash
from .validation import validate_scenarios, validate_selection


def derive_scenario_results(common: dict[str, float], inputs: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for candidate_id, candidate in inputs.items():
        expected = annualized = downside = loss = expected_months = 0.0
        cases: dict[str, Any] = {}
        for scenario in SCENARIOS:
            case = dict(candidate[scenario])
            case["total_return"] = (case["target_price"] + case["dividend"]) / case[
                "current_price"
            ] - 1
            probability = common[scenario]
            months = case["realization_months"]
            if months <= 0:
                raise SemanticError("realization period must be positive")
            case["annualized_return"] = (1 + case["total_return"]) ** (12 / months) - 1
            expected += probability * case["total_return"]
            annualized += probability * case["annualized_return"]
            expected_months += probability * months
            downside += probability if case["total_return"] < 0 else 0
            loss += probability if case["permanent_loss"] else 0
            cases[scenario] = case
        output[candidate_id] = {
            "scenarios": cases,
            "probability_weighted_return": expected,
            "probability_weighted_annualized_return": annualized,
            "downside_probability": downside,
            "permanent_loss_probability": loss,
            "expected_realization_months": expected_months,
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
    risk_ineligible: set[str] | None = None,
) -> dict[str, Any]:
    risk_ineligible = risk_ineligible or set()
    excluded = {candidate for candidate, gates in hard_gates.items() if gates}
    eligible = [candidate for candidate in ranking if candidate not in excluded | risk_ineligible]
    attractive = bool(eligible and expected[eligible[0]] > benchmark_return)
    classifications = []
    selected_index = 0
    for candidate in ranking:
        if candidate in excluded:
            label = "EXCLUDED"
        elif candidate in risk_ineligible or not attractive:
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
        "overall_decision": "SELECTION" if attractive else "NO_SELECTION",
        "judgments": judgments,
        "risk_ineligible": sorted(risk_ineligible),
        "annualized_expected_returns": expected,
        "annualized_benchmark_return": benchmark_return,
    }
    validate_selection(payload)
    return payload


def select_from_analysis(
    risk_adjusted_ranking: list[str],
    hard_gates: dict[str, list[str]],
    scenario_results: dict[str, Any],
    cash_annual_return: float,
    investment_annual_return: float,
    max_downside_probability: float,
    max_permanent_loss_probability: float,
    judgments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive overall decision and at most two candidates from horizon-matched returns."""
    excluded = {candidate for candidate, gates in hard_gates.items() if gates}
    risk_ineligible: set[str] = set()
    benchmark = max(cash_annual_return, investment_annual_return)
    for candidate in risk_adjusted_ranking:
        result = scenario_results[candidate]
        if (
            candidate not in excluded
            and result["downside_probability"] <= max_downside_probability
            and result["permanent_loss_probability"] <= max_permanent_loss_probability
        ):
            continue
        risk_ineligible.add(candidate)
    expected = {
        candidate: scenario_results[candidate]["probability_weighted_annualized_return"]
        for candidate in scenario_results
    }
    return classify(
        risk_adjusted_ranking, hard_gates, expected, benchmark, judgments, risk_ineligible
    )


def update_diff(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    if old["generation_id"] == new["generation_id"]:
        raise SemanticError("update must create a generation")
    changes: list[dict[str, Any]] = []

    def walk(before: Any, after: Any, path: str) -> None:
        if path == "/generation_id":
            return
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after)):
                child = f"{path}/{key}"
                if key not in before:
                    changes.append(
                        {
                            "path": child,
                            "before": None,
                            "after": after[key],
                            "change": _change_type(child, "added"),
                        }
                    )
                elif key not in after:
                    changes.append(
                        {
                            "path": child,
                            "before": before[key],
                            "after": None,
                            "change": _change_type(child, "removed"),
                        }
                    )
                else:
                    walk(before[key], after[key], child)
        elif isinstance(before, list) and isinstance(after, list):
            if all(
                isinstance(item, dict) and ("candidate_id" in item or "evidence_id" in item)
                for item in before + after
            ):
                key = (
                    "candidate_id"
                    if any("candidate_id" in item for item in before + after)
                    else "evidence_id"
                )
                walk(
                    {item[key]: item for item in before}, {item[key]: item for item in after}, path
                )
            elif sorted(before, key=canonical_hash) != sorted(after, key=canonical_hash):
                changes.append(
                    {
                        "path": path,
                        "before": before,
                        "after": after,
                        "change": _change_type(path, "changed"),
                    }
                )
        elif before != after:
            changes.append(
                {
                    "path": path,
                    "before": before,
                    "after": after,
                    "change": _change_type(path, "changed"),
                }
            )

    walk(old, new, "")
    return changes


def _change_type(path: str, default: str) -> str:
    labels = {
        "classification": "classification_changed",
        "ranking": "ranking_changed",
        "assumption": "assumption_changed",
        "invalidation": "invalidation_triggered",
        "comparability": "comparability_changed",
    }
    for token, label in labels.items():
        if token in path:
            return label
    if "evidence" in path:
        return (
            "evidence_added"
            if default == "added"
            else "evidence_removed"
            if default == "removed"
            else default
        )
    if "candidates" in path:
        return (
            "candidate_added"
            if default == "added"
            else "candidate_removed"
            if default == "removed"
            else default
        )
    return default


def build_handoff(context: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    by_class: dict[str, list[str]] = {name: [] for name in CLASSIFICATIONS}
    for row in selection["classifications"]:
        by_class[row["classification"]].append(row["candidate_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": context["handoff_id"],
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
        "created_at": context["created_at"],
        "status": "active",
        "supersedes": context.get("supersedes"),
        "superseded_by": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "primary_candidate": by_class["PRIMARY"][0] if by_class["PRIMARY"] else None,
        "secondary_candidate": by_class["SECONDARY"][0] if by_class["SECONDARY"] else None,
        "conditional_candidates": by_class["CONDITIONAL"],
        "watch_candidates": by_class["WATCH"],
        "excluded_candidates": by_class["EXCLUDED"],
        "overall_decision": selection["overall_decision"],
        "recommended_next_action": "個別株完全分析"
        if not selection["no_selection"]
        else "NO_SELECTION",
    }
