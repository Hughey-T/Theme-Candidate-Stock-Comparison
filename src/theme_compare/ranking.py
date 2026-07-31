"""Recompute all rankings from atomic metrics; stored order is never authoritative."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import SemanticError, finite

RANKING_TYPES = ("company_quality", "tactical", "structural", "risk_adjusted", "portfolio_fit")
ELIGIBLE_STATES = {"observed", "estimated"}
ELIGIBLE_COMPARABILITY = {"comparable", "partially_comparable"}


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


def validate_stored_rankings(
    candidate_ids: list[str],
    metrics: list[dict[str, Any]],
    stored: dict[str, Any],
    excluded: set[str],
) -> dict[str, list[str]]:
    rankings, scores = derive_rankings(candidate_ids, metrics, excluded)
    if stored["ordered_candidates"] != rankings or stored["scores"] != scores:
        raise SemanticError("stored ranking or score mismatch")
    return rankings
