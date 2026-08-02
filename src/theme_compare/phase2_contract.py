"""Phase 2 contract guidance and bounded diagnostics for the Action API."""

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

_DIAGNOSTIC_LIMIT = 20
_METRIC_ERROR = "comparability matrix unknown or missing metric"
_COVERAGE_ERROR = "comparability matrix pair/metric coverage mismatch"


def enrich_phase2_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Expose the hidden Phase 2 semantic requirements in the next-contract response."""
    if contract.get("mode") != "initial" or contract.get("phase") != 2:
        return contract
    enriched = dict(contract)
    enriched["phase_requirements"] = INITIAL_PHASE2_REQUIREMENT
    return enriched


def rewrite_phase2_validation_error(exc: SemanticError, artifact: dict[str, Any]) -> SemanticError:
    """Replace generic Phase 2 errors with deterministic, bounded diagnostics."""
    if artifact.get("mode") != "initial" or artifact.get("phase") != 2:
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


def _metric_vocabulary(value: dict[str, Any]) -> tuple[list[str], list[str]]:
    candidate_rows = value.get("candidates", [])
    matrix_rows = value.get("comparability_matrix", [])
    expected = sorted(
        {
            metric
            for row in candidate_rows
            if isinstance(row, dict)
            for metric in (row.get("primary_metric"), row.get("secondary_metric"))
            if isinstance(metric, str)
        }
    )
    actual = sorted(
        {
            row.get("metric")
            for row in matrix_rows
            if isinstance(row, dict) and isinstance(row.get("metric"), str)
        }
    )
    return expected, actual


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
    candidates = sorted(
        {
            row.get("candidate_id")
            for row in value.get("candidates", [])
            if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
        }
    )
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
        if not all(isinstance(item, str) for item in (left, right, metric)):
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
