"""Phase-specific semantic dispatcher invoked by the persisted state machine."""

from __future__ import annotations
from typing import Any
from .models import SemanticError, finite, parse_rfc3339
from .ranking import validate_stored_rankings
from .validation import (
    validate_candidates,
    validate_evidence,
    validate_scenarios,
    validate_selection,
)


def validate_phase_artifact(state: dict[str, Any], artifact: dict[str, Any]) -> None:
    def validate_finite(value: Any, path: str = "payload") -> None:
        if isinstance(value, float):
            finite(value, path)
        elif isinstance(value, dict):
            for key, child in value.items():
                validate_finite(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                validate_finite(child, f"{path}[{index}]")

    validate_finite(artifact)
    active_artifacts = state["generation_history"][state["active_generation_id"]]["artifacts"]
    registry: dict[str, dict[str, Any]] = {}
    if artifact["mode"] == "update":
        for previous in state["generation_history"][state["initial_generation_id"]]["artifacts"]:
            registry = validate_evidence(previous, registry)
    for previous in active_artifacts:
        registry = validate_evidence(previous, registry)
    registry = validate_evidence(artifact, registry)

    def validate_payload_refs(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_refs":
                    if len(child) != len(set(child)) or any(ref not in registry for ref in child):
                        raise SemanticError("payload evidence reference mismatch")
                    candidate_id = value.get("candidate_id")
                    if candidate_id is not None and any(
                        registry[ref].get("candidate_id") not in (None, candidate_id)
                        for ref in child
                    ):
                        raise SemanticError("payload evidence candidate mismatch")
                else:
                    validate_payload_refs(child)
        elif isinstance(value, list):
            for child in value:
                validate_payload_refs(child)

    validate_payload_refs(artifact["payload"])
    mode, phase = artifact["mode"], artifact["phase"]
    payload = artifact["payload"]
    artifacts = active_artifacts

    def detailed() -> set[str]:
        if artifact["mode"] == "update":
            candidates = state["generation_history"][state["active_generation_id"]].get(
                "detailed_candidates", []
            )
            if candidates:
                return set(candidates)
        initial_artifacts = state["generation_history"][state["initial_generation_id"]]["artifacts"]
        if len(initial_artifacts) < 2:
            raise SemanticError("Phase 2 detailed candidates unavailable")
        return set(initial_artifacts[1]["payload"]["business_models"]["detailed_candidates"])

    def exact(rows: list[dict[str, Any]], label: str) -> None:
        ids = [row["candidate_id"] for row in rows]
        if len(ids) != len(set(ids)) or set(ids) != detailed():
            raise SemanticError(f"{label} candidate coverage mismatch")

    if mode == "initial" and phase == 1:
        value = payload["session_and_candidates"]
        validate_candidates(value["normalized_candidates"], value["candidate_set_id"])
        if value["candidate_set_id"] != state["candidate_set_id"]:
            raise SemanticError("Phase 1 candidate set mismatch")
        if parse_rfc3339(value["source_cutoff_at"]) > parse_rfc3339(value["comparison_as_of"]):
            raise SemanticError("Phase 1 future cutoff")
    elif mode == "initial" and phase == 2:
        value = payload["business_models"]
        candidates = {row["candidate_id"] for row in value["candidates"]}
        if set(value["detailed_candidates"]) != candidates:
            raise SemanticError("Phase 2 candidate coverage mismatch")
        for row in value["comparability_matrix"]:
            if (
                row["left_candidate_id"] not in candidates
                or row["right_candidate_id"] not in candidates
            ):
                raise SemanticError("comparability matrix references unknown candidate")
            if row["left_candidate_id"] == row["right_candidate_id"]:
                raise SemanticError("comparability matrix self-pair")
        phase1 = state["generation_history"][state["active_generation_id"]]["artifacts"][0]
        known = {
            row["candidate_id"]
            for row in phase1["payload"]["session_and_candidates"]["normalized_candidates"]
        }
        if not candidates <= known:
            raise SemanticError("Phase 2 candidate not present in Phase 1")
        metrics = {row["metric"] for row in value["comparability_matrix"]}
        allowed_metrics = {row["primary_metric"] for row in value["candidates"]} | {
            row["secondary_metric"] for row in value["candidates"]
        }
        if metrics != allowed_metrics and len(candidates) > 1:
            raise SemanticError("comparability matrix unknown or missing metric")
        seen: dict[tuple[str, str, str], str] = {}
        for row in value["comparability_matrix"]:
            left, right = sorted((row["left_candidate_id"], row["right_candidate_id"]))
            matrix_key = (left, right, row["metric"])
            if matrix_key in seen:
                raise SemanticError("duplicate or contradictory comparability pair/metric")
            seen[matrix_key] = row["comparability"]
        expected_pairs = {
            (left, right, metric)
            for index, left in enumerate(sorted(candidates))
            for right in sorted(candidates)[index + 1 :]
            for metric in metrics
        }
        if set(seen) != expected_pairs:
            raise SemanticError("comparability matrix pair/metric coverage mismatch")
    elif mode == "initial" and phase == 3:
        value = payload["theme_value_capture"]
        for key in ("theme_purity", "theme_sensitivity", "value_capture"):
            exact(value[key], f"Phase 3 {key}")
    elif mode == "initial" and phase == 4:
        value = payload["competitive_structure"]
        for key in ("current_competitive_advantage", "future_competitive_advantage"):
            exact(value[key], f"Phase 4 {key}")
    elif mode == "initial" and phase == 5:
        exact(payload["financial_conversion"]["conversion_paths"], "Phase 5")
    elif mode == "initial" and phase == 6:
        exact(payload["valuation_expectations"]["valuations"], "Phase 6")
    elif mode == "initial" and phase == 7:
        value = payload["common_scenarios"]
        results = {
            row["candidate_id"]: {key: item for key, item in row.items() if key != "candidate_id"}
            for row in value["company_results"]
        }
        validate_scenarios(value["probabilities"], results)
        exact(value["company_results"], "Phase 7")
    elif mode == "initial" and phase == 8:
        value = payload["catalysts"]
        exact(value["catalysts"], "Phase 8 catalysts")
        exact(value["rerating_paths"], "Phase 8 rerating paths")
        for catalyst in value["catalysts"]:
            absent = catalyst["status"] == "no_identified_catalyst"
            optional = (
                "event",
                "expected_date",
                "probability",
                "market_impact",
                "priced_in_level",
                "failure_impact",
            )
            if absent and (
                any(catalyst[key] is not None for key in optional) or catalyst["evidence_refs"]
            ):
                raise SemanticError("no-identified-catalyst record contains event data")
            if not absent and (
                any(catalyst[key] is None for key in optional) or not catalyst["evidence_refs"]
            ):
                raise SemanticError("identified catalyst is incomplete")
    elif mode == "initial" and phase == 9:
        exact(payload["risks_and_stress"]["company_risks"], "Phase 9")
    elif mode == "initial" and phase == 10:
        value = payload["final_selection"]
        expected_candidates = detailed()
        if set(value["candidate_ids"]) != expected_candidates or len(value["candidate_ids"]) != len(
            expected_candidates
        ):
            raise SemanticError("Phase 10 candidate_ids coverage mismatch")
        metric_coverage = {
            ranking_type: [
                row["candidate_id"]
                for row in value["atomic_ranking_metrics"]
                if row["ranking_type"] == ranking_type
            ]
            for ranking_type in value["stored_rankings"]
        }
        for ranking_type, ids in metric_coverage.items():
            if len(ids) != len(set(ids)) or set(ids) != expected_candidates:
                raise SemanticError(f"Phase 10 {ranking_type} metric coverage mismatch")
        for ranking_type, ranking in value["stored_rankings"].items():
            if len(ranking) != len(set(ranking)) or set(ranking) != expected_candidates:
                raise SemanticError(f"Phase 10 {ranking_type} ranking coverage mismatch")
            if set(value["stored_scores"][ranking_type]) != expected_candidates:
                raise SemanticError(f"Phase 10 {ranking_type} score coverage mismatch")
        exact(value["scenario_results"], "Phase 10 scenario")
        exact(value["classifications"], "Phase 10 classification")
        if set(value["hard_gates"]) != expected_candidates:
            raise SemanticError("Phase 10 hard gate coverage mismatch")
        excluded = {candidate for candidate, gates in value["hard_gates"].items() if gates}
        validate_stored_rankings(
            value["candidate_ids"],
            value["atomic_ranking_metrics"],
            {
                "ordered_candidates": value["stored_rankings"],
                "scores": value.get("stored_scores", {}),
            },
            excluded,
        )
        results = {
            row["candidate_id"]: {key: item for key, item in row.items() if key != "candidate_id"}
            for row in value["scenario_results"]
        }
        validate_scenarios(value["scenario_probabilities"], results)
        artifacts = state["generation_history"][state["active_generation_id"]]["artifacts"]
        phase7 = artifacts[6]["payload"]["common_scenarios"]
        if (
            value["scenario_probabilities"] != phase7["probabilities"]
            or value["scenario_results"] != phase7["company_results"]
        ):
            raise SemanticError("Phase 10 scenario results differ from validated Phase 7")
        limits = value["risk_limits"]
        risk_ineligible = {
            candidate
            for candidate, result in results.items()
            if result["downside_probability"] > limits["max_downside_probability"]
            or result["permanent_loss_probability"] > limits["max_permanent_loss_probability"]
        }
        benchmark = max(value["benchmark_inputs"].values())
        returns = {
            candidate: result["probability_weighted_annualized_return"]
            for candidate, result in results.items()
        }
        decision = value["overall_decision"]
        validate_selection(
            {
                "classifications": value["classifications"],
                "hard_gates": value["hard_gates"],
                "ranking": value["stored_rankings"]["risk_adjusted"],
                "risk_ineligible": list(risk_ineligible),
                "annualized_expected_returns": returns,
                "annualized_benchmark_return": benchmark,
                "absolute_attractiveness": decision == "SELECTION",
                "no_selection": decision == "NO_SELECTION",
                "overall_decision": decision,
                "judgments": artifact["judgments"],
            }
        )
        primary = next(
            (
                row["candidate_id"]
                for row in value["classifications"]
                if row["classification"] == "PRIMARY"
            ),
            None,
        )
        secondary = next(
            (
                row["candidate_id"]
                for row in value["classifications"]
                if row["classification"] == "SECONDARY"
            ),
            None,
        )
        handoff = value["handoff"]
        classified = {
            label: {
                row["candidate_id"]
                for row in value["classifications"]
                if row["classification"] == label
            }
            for label in ("CONDITIONAL", "WATCH", "EXCLUDED")
        }
        if (
            handoff["primary_candidate"] != primary
            or handoff["secondary_candidate"] != secondary
            or handoff["overall_decision"] != decision
            or set(handoff["conditional_candidates"]) != classified["CONDITIONAL"]
            or set(handoff["watch_candidates"]) != classified["WATCH"]
            or set(handoff["excluded_candidates"]) != classified["EXCLUDED"]
        ):
            raise SemanticError("Phase 10 handoff differs from selection")
    elif mode == "update" and phase == 1:
        value = payload["update_diff"]
        if (
            value["old_generation"]["generation_id"] != state["previous_generation_id"]
            or value["new_generation"]["generation_id"] != state["active_generation_id"]
        ):
            raise SemanticError("update generation lineage mismatch")
        previous_entry = state["generation_history"][state["previous_generation_id"]]
        previous = set(previous_entry["detailed_candidates"])
        updated = set(value["updated_detailed_candidates"])
        if set(value["previous_detailed_candidates"]) != previous:
            raise SemanticError("previous detailed candidate mismatch")
        if set(value["added_candidates"]) != updated - previous:
            raise SemanticError("added candidate mismatch")
        if set(value["removed_candidates"]) != previous - updated:
            raise SemanticError("removed candidate mismatch")
        if set(value["retained_candidates"]) != previous & updated:
            raise SemanticError("retained candidate mismatch")
        validate_candidates(value["normalized_candidates"], value["updated_candidate_set_id"])
        if value["updated_candidate_set_id"] != state["candidate_set_id"]:
            raise SemanticError("updated candidate set mismatch")
        if not updated <= {row["candidate_id"] for row in value["normalized_candidates"]}:
            raise SemanticError("updated candidate identity coverage mismatch")
    elif mode == "update" and phase == 2:
        value = payload["updated_selection"]
        if (
            state["active_handoff_id"] is not None
            and value["superseded_handoff_id"] != state["active_handoff_id"]
        ):
            raise SemanticError("handoff supersession mismatch")
        expected_candidates = detailed()
        if set(value["candidate_ids"]) != expected_candidates:
            raise SemanticError("updated selection candidate coverage mismatch")
        excluded = {candidate for candidate, gates in value["hard_gates"].items() if gates}
        validate_stored_rankings(
            value["candidate_ids"],
            value["atomic_ranking_metrics"],
            {"ordered_candidates": value["stored_rankings"], "scores": value["stored_scores"]},
            excluded,
        )
        results = {
            row["candidate_id"]: {key: item for key, item in row.items() if key != "candidate_id"}
            for row in value["scenario_results"]
        }
        if set(results) != expected_candidates:
            raise SemanticError("updated scenario coverage mismatch")
        validate_scenarios(value["scenario_probabilities"], results)
        benchmark = max(value["benchmark_inputs"].values())
        finite(benchmark, "updated benchmark")
        limits = value["risk_limits"]
        risk_ineligible = {
            candidate
            for candidate, result in results.items()
            if result["downside_probability"] > limits["max_downside_probability"]
            or result["permanent_loss_probability"] > limits["max_permanent_loss_probability"]
        }
        decision = value["overall_decision"]
        validate_selection(
            {
                "classifications": value["classifications"],
                "hard_gates": value["hard_gates"],
                "ranking": value["stored_rankings"]["risk_adjusted"],
                "risk_ineligible": list(risk_ineligible),
                "annualized_expected_returns": {
                    candidate: result["probability_weighted_annualized_return"]
                    for candidate, result in results.items()
                },
                "annualized_benchmark_return": benchmark,
                "absolute_attractiveness": decision == "SELECTION",
                "no_selection": decision == "NO_SELECTION",
                "overall_decision": decision,
                "judgments": artifact["judgments"],
            }
        )
        reference = value["updated_handoff"]
        primary = next(
            (
                row["candidate_id"]
                for row in value["classifications"]
                if row["classification"] == "PRIMARY"
            ),
            None,
        )
        secondary = next(
            (
                row["candidate_id"]
                for row in value["classifications"]
                if row["classification"] == "SECONDARY"
            ),
            None,
        )
        classes = {
            label: {
                row["candidate_id"]
                for row in value["classifications"]
                if row["classification"] == label
            }
            for label in ("CONDITIONAL", "WATCH", "EXCLUDED")
        }
        old_id = state["active_handoff_id"]
        if (
            reference["overall_decision"] != decision
            or reference["primary_candidate"] != primary
            or reference["secondary_candidate"] != secondary
            or set(reference["conditional_candidates"]) != classes["CONDITIONAL"]
            or set(reference["watch_candidates"]) != classes["WATCH"]
            or set(reference["excluded_candidates"]) != classes["EXCLUDED"]
            or reference["generation_id"] != state["active_generation_id"]
            or reference["candidate_set_id"] != state["candidate_set_id"]
            or reference["supersedes"] != old_id
            or reference["handoff_id"] == old_id
            or reference["handoff_id"] in state["handoff_history"]
        ):
            raise SemanticError("updated handoff differs from validated selection or lifecycle")
        if decision == "NO_SELECTION" and (primary is not None or secondary is not None):
            raise SemanticError("NO_SELECTION updated handoff has selected candidates")
