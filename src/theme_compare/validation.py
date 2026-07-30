"""Semantic validation, deliberately independent from JSON Schema."""

from __future__ import annotations

from typing import Any

from .constants import HARD_GATES, SCENARIOS
from .models import SemanticError, candidate_set_id, finite, parse_rfc3339, require_rfc3339


def validate_candidates(candidates: list[dict[str, Any]], declared_set_id: str) -> None:
    if not 1 <= len(candidates) <= 12:
        raise SemanticError("candidate count must be 1..12")
    ids = [c["candidate_id"] for c in candidates]
    if len(ids) != len(set(ids)):
        raise SemanticError("duplicate candidate_id")
    legal_keys: set[tuple[str, str, str, str, bool]] = set()
    aliases: set[str] = set()
    for candidate in candidates:
        key = (
            candidate["issuer_id"],
            candidate["ticker"].upper(),
            candidate["exchange"].upper(),
            candidate["share_class"],
            candidate["is_adr"],
        )
        if key in legal_keys:
            raise SemanticError("duplicate legal security identity")
        legal_keys.add(key)
        names = {candidate["ticker"].upper(), *(x.upper() for x in candidate["former_tickers"])}
        if aliases & names:
            raise SemanticError("ticker/former-ticker/corporate-action overlap")
        aliases |= names
    if candidate_set_id(candidates) != declared_set_id:
        raise SemanticError("candidate_set_id mismatch")


def validate_scenarios(common: dict[str, float], results: dict[str, Any]) -> None:
    if set(common) != set(SCENARIOS) or abs(sum(common.values()) - 1.0) > 1e-9:
        raise SemanticError("common scenario probabilities must total 1")
    for probability in common.values():
        finite(probability, "probability")
        if not 0 <= probability <= 1:
            raise SemanticError("invalid probability")
    for candidate_id, result in results.items():
        cases = result["scenarios"]
        if set(cases) != set(SCENARIOS):
            raise SemanticError(f"scenario mismatch: {candidate_id}")
        expected = 0.0
        downside = 0.0
        loss = 0.0
        for name, probability in common.items():
            case = cases[name]
            for field in ("current_price", "target_price", "diluted_shares", "dividend"):
                finite(case[field], field)
                if case[field] < 0 or (
                    field in {"current_price", "diluted_shares"} and case[field] == 0
                ):
                    raise SemanticError(f"invalid {field}")
            total_return = (case["target_price"] + case["dividend"]) / case["current_price"] - 1
            if abs(total_return - case["total_return"]) > 1e-8:
                raise SemanticError("total return mismatch or dividend double-count")
            expected += probability * total_return
            if total_return < 0:
                downside += probability
            if case["permanent_loss"]:
                loss += probability
        if abs(expected - result["probability_weighted_return"]) > 1e-8:
            raise SemanticError("probability-weighted return mismatch")
        if abs(downside - result["downside_probability"]) > 1e-8:
            raise SemanticError("downside probability mismatch")
        if abs(loss - result["permanent_loss_probability"]) > 1e-8:
            raise SemanticError("permanent-loss probability mismatch")


def validate_selection(payload: dict[str, Any]) -> None:
    classifications = payload["classifications"]
    ids = [x["candidate_id"] for x in classifications]
    if len(ids) != len(set(ids)):
        raise SemanticError("classification is not exclusive")
    selected = [x for x in classifications if x["classification"] in {"PRIMARY", "SECONDARY"}]
    excluded = {x["candidate_id"] for x in classifications if x["classification"] == "EXCLUDED"}
    if len(selected) > 2 or any(x["candidate_id"] in excluded for x in selected):
        raise SemanticError("invalid handoff selection")
    gate_map = payload["hard_gates"]
    for candidate_id, gates in gate_map.items():
        if any(g not in HARD_GATES for g in gates):
            raise SemanticError("unknown hard gate")
        if gates and candidate_id not in excluded:
            raise SemanticError("hard gate cannot be offset by score")
    primary = [x["candidate_id"] for x in classifications if x["classification"] == "PRIMARY"]
    risk_ineligible = set(payload.get("risk_ineligible", []))
    eligible_ranking = [x for x in payload["ranking"] if x not in excluded | risk_ineligible]
    returns = payload["annualized_expected_returns"]
    benchmark = payload["annualized_benchmark_return"]
    recomputed_attractive = bool(eligible_ranking and returns[eligible_ranking[0]] > benchmark)
    expected_primary = eligible_ranking[:1] if recomputed_attractive else []
    if primary != expected_primary:
        raise SemanticError("ranking/winner/no-selection mismatch")
    if payload["absolute_attractiveness"] != recomputed_attractive:
        raise SemanticError("absolute attractiveness mismatch")
    if payload["no_selection"] != (not recomputed_attractive):
        raise SemanticError("NO_SELECTION flag mismatch")
    expected_decision = "NO_SELECTION" if payload["no_selection"] else "SELECTION"
    if payload.get("overall_decision") != expected_decision:
        raise SemanticError("overall decision mismatch")
    if payload["no_selection"] and selected:
        raise SemanticError("NO_SELECTION cannot have handoff candidates")
    for judgment in payload["judgments"]:
        if not judgment["evidence_refs"] or not judgment["contrary_evidence_refs"]:
            raise SemanticError("judgment requires evidence and contrary evidence")
    expected_secondary = (
        [candidate for candidate in eligible_ranking[1:] if returns[candidate] > benchmark][:1]
        if recomputed_attractive
        else []
    )
    actual_secondary = [
        x["candidate_id"] for x in classifications if x["classification"] == "SECONDARY"
    ]
    if actual_secondary != expected_secondary:
        raise SemanticError("secondary mismatch")


def validate_envelope(envelope: dict[str, Any]) -> None:
    comparison = parse_rfc3339(envelope["comparison_as_of"])
    cutoff = parse_rfc3339(envelope["source_cutoff_at"])
    if cutoff > comparison:
        raise SemanticError("future information detected")
    generation = envelope["generation_id"]
    candidate_set = envelope["candidate_set_id"]
    for artifact in envelope["artifacts"]:
        if artifact["generation_id"] != generation:
            raise SemanticError("mixed-generation")
        if artifact["candidate_set_id"] != candidate_set:
            raise SemanticError("mixed candidate set")
        if artifact["source_cutoff_at"] != envelope["source_cutoff_at"]:
            raise SemanticError("mixed source cutoff")
        require_rfc3339(artifact["source_cutoff_at"])


def validate_scores(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        dependencies: set[str] = set()
        for metric in row["metrics"]:
            if metric["comparability"] == "not_comparable" and metric["weight"] != 0:
                raise SemanticError("non-comparable metric was scored")
            if (
                metric["state"] in {"missing", "not_applicable", "not_evaluable", "stale"}
                and metric["weight"] != 0
            ):
                raise SemanticError("unusable datum was scored")
            root = metric["dependency_root"]
            if metric["weight"] and root in dependencies:
                raise SemanticError("double counting dependency root")
            if metric["weight"]:
                dependencies.add(root)
