"""Phase-specific semantic dispatcher invoked by the persisted state machine."""

from __future__ import annotations
from typing import Any
from .models import SemanticError, parse_rfc3339
from .ranking import validate_stored_rankings
from .validation import (
    validate_candidates,
    validate_evidence,
    validate_scenarios,
    validate_selection,
)


def validate_phase_artifact(state: dict[str, Any], artifact: dict[str, Any]) -> None:
    validate_evidence(artifact)
    mode, phase = artifact["mode"], artifact["phase"]
    payload = artifact["payload"]
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
    elif mode == "initial" and phase == 7:
        value = payload["common_scenarios"]
        results = {
            row["candidate_id"]: {key: item for key, item in row.items() if key != "candidate_id"}
            for row in value["company_results"]
        }
        validate_scenarios(value["probabilities"], results)
    elif mode == "initial" and phase == 10:
        value = payload["final_selection"]
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
        if (
            handoff["primary_candidate"] != primary
            or handoff["secondary_candidate"] != secondary
            or handoff["overall_decision"] != decision
        ):
            raise SemanticError("Phase 10 handoff differs from selection")
    elif mode == "update" and phase == 1:
        value = payload["update_diff"]
        if (
            value["old_generation"]["generation_id"] != state["previous_generation_id"]
            or value["new_generation"]["generation_id"] != state["active_generation_id"]
        ):
            raise SemanticError("update generation lineage mismatch")
    elif mode == "update" and phase == 2:
        value = payload["updated_selection"]
        if (
            state["active_handoff_id"] is not None
            and value["superseded_handoff_id"] != state["active_handoff_id"]
        ):
            raise SemanticError("handoff supersession mismatch")
