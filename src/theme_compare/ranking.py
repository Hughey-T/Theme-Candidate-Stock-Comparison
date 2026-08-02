"""Recompute all rankings from atomic metrics; stored order is never authoritative."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .models import SemanticError, finite

RANKING_TYPES = ("company_quality", "tactical", "structural", "risk_adjusted", "portfolio_fit")
ELIGIBLE_STATES = {"observed", "estimated"}
ELIGIBLE_COMPARABILITY = {"comparable", "partially_comparable"}
_DIAGNOSTIC_LIMIT = 50


def derive_rankings(
    candidate_ids: list[str], metrics: list[dict[str, Any]], excluded: set[str] | None = None
) -> tuple[dict[str, list[str]], dict[str, dict[str, float]]]:
    """Normalize weighted atomic metrics and rank with candidate-id tie breaking."""
    if len(candidate_ids) != len(set(candidate_ids)):
        raise SemanticError("duplicated candidate")
    known = set(candidate_ids)
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    weights: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    dependencies: dict[tuple[str, str], set[str]] = defaultdict(set)
    coverage: dict[str, set[str]] = defaultdict(set)
    for metric in metrics:
        candidate = metric["candidate_id"]
        ranking_type = metric["ranking_type"]
        if candidate not in known or ranking_type not in RANKING_TYPES:
            raise SemanticError("unknown candidate or ranking type")
        finite(metric["value"], "metric value")
        finite(metric["weight"], "metric weight")
        if not 0 <= metric["value"] <= 1 or metric["weight"] < 0:
            raise SemanticError("metrics must be normalized and weights non-negative")
        usable = (
            metric["applicable"]
            and metric["state"] in ELIGIBLE_STATES
            and metric["comparability"] in ELIGIBLE_COMPARABILITY
        )
        effective = metric["weight"] if usable else 0.0
        if metric.get("effective_weight", effective) != effective:
            raise SemanticError("effective weight mismatch")
        root = metric["dependency_root"]
        key = (candidate, ranking_type)
        if effective and root in dependencies[key]:
            raise SemanticError("double counting dependency root")
        if effective:
            dependencies[key].add(root)
            totals[candidate][ranking_type] += metric["value"] * effective
            weights[candidate][ranking_type] += effective
        coverage[candidate].add(ranking_type)
    if set(coverage) != known or any(
        coverage[candidate] != set(RANKING_TYPES) for candidate in known
    ):
        raise SemanticError("incomplete candidate/ranking coverage")
    scores: dict[str, dict[str, float]] = {name: {} for name in RANKING_TYPES}
    rankings: dict[str, list[str]] = {}
    for ranking_type in RANKING_TYPES:
        for candidate in candidate_ids:
            denominator = weights[candidate][ranking_type]
            if denominator <= 0:
                raise SemanticError("eligible metric weight must be positive")
            scores[ranking_type][candidate] = totals[candidate][ranking_type] / denominator
        rankings[ranking_type] = sorted(
            candidate_ids,
            key=lambda candidate: (-scores[ranking_type][candidate], candidate),
        )
    return rankings, scores


def _ranking_mismatch_diagnostic(
    expected_rankings: dict[str, list[str]],
    expected_scores: dict[str, dict[str, float]],
    actual_rankings: dict[str, list[str]],
    actual_scores: dict[str, dict[str, float]],
) -> dict[str, Any]:
    expected_types = set(RANKING_TYPES)
    actual_ranking_types = set(actual_rankings)
    actual_score_types = set(actual_scores)
    missing_ranking_types = sorted(
        (expected_types - actual_ranking_types) | (expected_types - actual_score_types)
    )
    extra_ranking_types = sorted(
        (actual_ranking_types - expected_types) | (actual_score_types - expected_types)
    )

    ranking_mismatches: list[dict[str, Any]] = []
    score_mismatches: list[dict[str, Any]] = []
    missing_candidates: list[dict[str, str]] = []
    extra_candidates: list[dict[str, str]] = []

    for ranking_type in RANKING_TYPES:
        expected_order = expected_rankings[ranking_type]
        actual_order = actual_rankings.get(ranking_type, [])
        if actual_order != expected_order:
            ranking_mismatches.append(
                {
                    "ranking_type": ranking_type,
                    "expected": expected_order,
                    "actual": actual_order,
                }
            )

        expected_candidate_set = set(expected_scores[ranking_type])
        actual_score_map = actual_scores.get(ranking_type, {})
        actual_candidate_set = set(actual_score_map)
        ranking_candidate_set = set(actual_order)
        for candidate in sorted(
            (expected_candidate_set - actual_candidate_set)
            | (expected_candidate_set - ranking_candidate_set)
        ):
            missing_candidates.append({"ranking_type": ranking_type, "candidate_id": candidate})
        for candidate in sorted(
            (actual_candidate_set - expected_candidate_set)
            | (ranking_candidate_set - expected_candidate_set)
        ):
            extra_candidates.append({"ranking_type": ranking_type, "candidate_id": candidate})
        for candidate in sorted(expected_candidate_set & actual_candidate_set):
            expected_score = expected_scores[ranking_type][candidate]
            actual_score = actual_score_map[candidate]
            if actual_score != expected_score:
                score_mismatches.append(
                    {
                        "ranking_type": ranking_type,
                        "candidate_id": candidate,
                        "expected": expected_score,
                        "actual": actual_score,
                    }
                )

    return {
        "expected_rankings": expected_rankings,
        "actual_rankings": actual_rankings,
        "expected_scores": expected_scores,
        "actual_scores": actual_scores,
        "ranking_mismatches": ranking_mismatches[:_DIAGNOSTIC_LIMIT],
        "ranking_mismatches_total": len(ranking_mismatches),
        "score_mismatches": score_mismatches[:_DIAGNOSTIC_LIMIT],
        "score_mismatches_total": len(score_mismatches),
        "missing_ranking_types": missing_ranking_types[:_DIAGNOSTIC_LIMIT],
        "missing_ranking_types_total": len(missing_ranking_types),
        "extra_ranking_types": extra_ranking_types[:_DIAGNOSTIC_LIMIT],
        "extra_ranking_types_total": len(extra_ranking_types),
        "missing_candidates": missing_candidates[:_DIAGNOSTIC_LIMIT],
        "missing_candidates_total": len(missing_candidates),
        "extra_candidates": extra_candidates[:_DIAGNOSTIC_LIMIT],
        "extra_candidates_total": len(extra_candidates),
        "diagnostic_limit": _DIAGNOSTIC_LIMIT,
    }


def validate_stored_rankings(
    candidate_ids: list[str],
    metrics: list[dict[str, Any]],
    stored: dict[str, Any],
    excluded: set[str],
) -> dict[str, list[str]]:
    rankings, scores = derive_rankings(candidate_ids, metrics, excluded)
    actual_rankings = stored["ordered_candidates"]
    actual_scores = stored["scores"]
    if actual_rankings != rankings or actual_scores != scores:
        details = _ranking_mismatch_diagnostic(rankings, scores, actual_rankings, actual_scores)
        raise SemanticError(
            "stored ranking or score mismatch: "
            + json.dumps(details, sort_keys=True, separators=(",", ":"))
        )
    return rankings
