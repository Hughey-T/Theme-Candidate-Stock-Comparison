"""Phase-specific contract guidance and bounded diagnostics for the Action API."""

from __future__ import annotations

import json
from typing import Any

from .models import SemanticError

INITIAL_PHASE2_REQUIREMENT = (
    "Classify business models and select detailed candidates. Treat the unique union of every "
    "candidate row's primary_metric and secondary_metric as the authoritative metric vocabulary. "
    "The comparability_matrix must contain exactly one row for every unordered candidate pair "
    "multiplied by every metric in that vocabulary. Self-pairs, duplicate pair/metric rows, "
    "missing rows, and extra rows are forbidden. detailed_candidates must exactly equal the "
    "candidate_id set in candidates. Required matrix row count is "
    "combination(candidate_count, 2) × unique_metric_count."
)

INITIAL_PHASE10_REQUIREMENT = (
    "Recalculate ranking and typed handoff. The authoritative ranking types are company_quality, "
    "tactical, structural, risk_adjusted, and portfolio_fit. atomic_ranking_metrics must cover "
    "every candidate × every ranking type. Each value must be within [0,1] and each weight must be "
    "non-negative. A metric is usable only when applicable is true, state is observed or estimated, "
    "and comparability is comparable or partially_comparable. For a usable metric, "
    "effective_weight must exactly equal weight; otherwise effective_weight must be 0. Each "
    "candidate × ranking type must have positive total usable weight, and a positive-weight "
    "dependency_root may appear only once within that candidate × ranking type. Compute each exact "
    "stored score as sum(value * effective_weight) / sum(effective_weight), without display rounding. "
    "Order candidates by exact score descending, with candidate_id ascending as the deterministic "
    "tie-break. stored_scores and stored_rankings must be complete maps and must exactly equal these "
    "runtime derivations; do not use rounded scores or prose ranking order. hard_gates must be an "
    "object whose key set exactly equals candidate_ids. Every candidate must have a key even when "
    "no hard gate applies; represent that case with an empty array, for example candidate_id: []. "
    "Each non-empty gate entry must be a non-empty string. An empty hard_gates object, missing "
    "candidate keys, and extra candidate keys are forbidden."
)

_DIAGNOSTIC_LIMIT = 20
_METRIC_ERROR = "comparability matrix unknown or missing metric"
_COVERAGE_ERROR = "comparability matrix pair/metric coverage mismatch"


def enrich_phase2_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Expose hidden Initial Phase 2 and Phase 10 requirements in next-contract responses."""
    if contract.get("mode") != "initial":
        return contract
    phase = contract.get("phase")
    if phase == 2:
        requirement = INITIAL_PHASE2_REQUIREMENT
    elif phase == 10:
        requirement = INITIAL_PHASE10_REQUIREMENT
    else:
        return contract
    enriched = dict(contract)
    enriched["phase_requirements"] = requirement
    return enriched


def rewrite_phase2_validation_error(exc: SemanticError, artifact: dict[str, Any]) -> SemanticError:
    """Replace generic phase errors with deterministic, bounded diagnostics."""
    if artifact.get("mode") != "initial":
        return exc
    if artifact.get("phase") == 10:
        return _rewrite_phase10_hard_gates_error(exc, artifact)
    if artifact.get("phase") != 2:
        return exc

    business_models = artifact.get("payload", {}).get("business_models")
    if not isinstance(business_models, dict):
        return exc

    message = str(exc)
    if message == _METRIC_ERROR:
        return SemanticError(_metric_diagnostic(business_models))
    if message == _COVERAGE_ERROR:
        return SemanticError(_coverage_diagnostic(business_models))
    return exc


def _rewrite_phase10_hard_gates_error(
    exc: SemanticError, artifact: dict[str, Any]
) -> SemanticError:
    selection = artifact.get("payload", {}).get("final_selection")
    if not isinstance(selection, dict):
        return exc
    candidate_ids = selection.get("candidate_ids")
    if not isinstance(candidate_ids, list) or not all(
        isinstance(candidate, str) and candidate for candidate in candidate_ids
    ):
        return exc

    expected = sorted(set(candidate_ids))
    hard_gates = selection.get("hard_gates")
    actual = sorted(hard_gates) if isinstance(hard_gates, dict) else []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    invalid_values: list[dict[str, str]] = []
    if isinstance(hard_gates, dict):
        for candidate in actual:
            gates = hard_gates[candidate]
            if not isinstance(gates, list):
                invalid_values.append(
                    {"candidate_id": candidate, "reason": "value must be an array"}
                )
            elif any(not isinstance(gate, str) or not gate for gate in gates):
                invalid_values.append(
                    {
                        "candidate_id": candidate,
                        "reason": "every gate must be a non-empty string",
                    }
                )
    else:
        invalid_values.append({"candidate_id": "*", "reason": "hard_gates must be an object"})

    if not missing and not extra and not invalid_values and hard_gates:
        return exc

    expected_hard_gates: dict[str, list[str]] = {}
    for candidate in expected:
        gates = hard_gates.get(candidate) if isinstance(hard_gates, dict) else None
        if isinstance(gates, list) and all(isinstance(gate, str) and gate for gate in gates):
            expected_hard_gates[candidate] = list(gates)
        else:
            expected_hard_gates[candidate] = []

    details = {
        "expected_candidates": expected[:_DIAGNOSTIC_LIMIT],
        "expected_candidates_total": len(expected),
        "actual_candidates": actual[:_DIAGNOSTIC_LIMIT],
        "actual_candidates_total": len(actual),
        "missing_candidates": missing[:_DIAGNOSTIC_LIMIT],
        "missing_candidates_total": len(missing),
        "extra_candidates": extra[:_DIAGNOSTIC_LIMIT],
        "extra_candidates_total": len(extra),
        "invalid_gate_values": invalid_values[:_DIAGNOSTIC_LIMIT],
        "invalid_gate_values_total": len(invalid_values),
        "expected_hard_gates": expected_hard_gates,
        "diagnostic_limit": _DIAGNOSTIC_LIMIT,
    }
    return SemanticError(
        "Phase 10 hard_gates contract mismatch: "
        + json.dumps(details, sort_keys=True, separators=(",", ":"))
    )


def _metric_vocabulary(value: dict[str, Any]) -> tuple[list[str], list[str]]:
    expected_set: set[str] = set()
    for row in value.get("candidates", []):
        if not isinstance(row, dict):
            continue
        for key in ("primary_metric", "secondary_metric"):
            metric = row.get(key)
            if isinstance(metric, str):
                expected_set.add(metric)

    actual_set: set[str] = set()
    for row in value.get("comparability_matrix", []):
        if not isinstance(row, dict):
            continue
        metric = row.get("metric")
        if isinstance(metric, str):
            actual_set.add(metric)

    return sorted(expected_set), sorted(actual_set)


def _metric_diagnostic(value: dict[str, Any]) -> str:
    expected, actual = _metric_vocabulary(value)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    details = {
        "expected_metrics": expected[:_DIAGNOSTIC_LIMIT],
        "expected_metrics_total": len(expected),
        "actual_metrics": actual[:_DIAGNOSTIC_LIMIT],
        "actual_metrics_total": len(actual),
        "missing_metrics": missing[:_DIAGNOSTIC_LIMIT],
        "missing_metrics_total": len(missing),
        "extra_metrics": extra[:_DIAGNOSTIC_LIMIT],
        "extra_metrics_total": len(extra),
        "diagnostic_limit": _DIAGNOSTIC_LIMIT,
    }
    return "comparability matrix metric vocabulary mismatch: " + json.dumps(
        details, sort_keys=True, separators=(",", ":")
    )


def _pair_metric_rows(
    value: dict[str, Any],
) -> tuple[
    set[tuple[str, str, str]],
    set[tuple[str, str, str]],
]:
    candidate_ids: set[str] = set()
    for row in value.get("candidates", []):
        if not isinstance(row, dict):
            continue
        candidate_id = row.get("candidate_id")
        if isinstance(candidate_id, str):
            candidate_ids.add(candidate_id)
    candidates = sorted(candidate_ids)

    metrics, _ = _metric_vocabulary(value)
    expected = {
        (left, right, metric)
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
        for metric in metrics
    }
    actual: set[tuple[str, str, str]] = set()
    for row in value.get("comparability_matrix", []):
        if not isinstance(row, dict):
            continue
        left = row.get("left_candidate_id")
        right = row.get("right_candidate_id")
        metric = row.get("metric")
        if not isinstance(left, str) or not isinstance(right, str) or not isinstance(metric, str):
            continue
        first, second = sorted((left, right))
        actual.add((first, second, metric))
    return expected, actual


def _render_pair_metric(item: tuple[str, str, str]) -> dict[str, str]:
    left, right, metric = item
    return {
        "left_candidate_id": left,
        "right_candidate_id": right,
        "metric": metric,
    }


def _coverage_diagnostic(value: dict[str, Any]) -> str:
    expected, actual = _pair_metric_rows(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details = {
        "expected_count": len(expected),
        "actual_count": len(actual),
        "missing_pair_metrics": [_render_pair_metric(item) for item in missing[:_DIAGNOSTIC_LIMIT]],
        "missing_pair_metrics_total": len(missing),
        "extra_pair_metrics": [_render_pair_metric(item) for item in extra[:_DIAGNOSTIC_LIMIT]],
        "extra_pair_metrics_total": len(extra),
        "diagnostic_limit": _DIAGNOSTIC_LIMIT,
    }
    return "comparability matrix pair/metric coverage mismatch: " + json.dumps(
        details, sort_keys=True, separators=(",", ":")
    )
