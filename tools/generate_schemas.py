"""Generate all closed Draft 2020-12 contracts from canonical vocabulary."""

from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
STRING = {"type": "string", "minLength": 1}
DT = {"type": "string", "format": "date-time", "pattern": r"(Z|[+-]\d\d:\d\d)$"}


def closed(p, required=None):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": p,
        "required": required or list(p),
    }


def main():
    from theme_compare.constants import (
        CLASSIFICATIONS,
        PERSISTENCE,
        SCENARIOS,
    )

    candidate = closed(
        {
            "candidate_id": STRING,
            "issuer_id": STRING,
            "issuer_name": STRING,
            "ticker": STRING,
            "exchange": STRING,
            "share_class": STRING,
            "is_adr": {"type": "boolean"},
            "underlying_security_id": {"type": ["string", "null"]},
            "former_tickers": {"type": "array", "items": STRING, "uniqueItems": True},
            "corporate_action_lineage": {"type": "array", "items": STRING, "uniqueItems": True},
            "listing_country": STRING,
        }
    )
    evidence_base = {
        "evidence_id": STRING,
        "candidate_id": {"type": ["string", "null"]},
        "statement": STRING,
        "as_of": DT,
    }
    judgment = closed(
        {
            "judgment": STRING,
            "evidence_refs": {"type": "array", "items": STRING, "minItems": 1, "uniqueItems": True},
            "contrary_evidence_refs": {
                "type": "array",
                "items": STRING,
                "minItems": 1,
                "uniqueItems": True,
            },
            "confidence": {"enum": ["low", "medium", "high"]},
            "assumptions": {"type": "array", "items": STRING},
            "invalidation_conditions": {"type": "array", "items": STRING, "minItems": 1},
        }
    )
    fact = closed({**evidence_base, "source_type": {"const": "FACT"}})
    claim = closed({**evidence_base, "source_type": {"const": "COMPANY_CLAIM"}})
    estimate = closed({**evidence_base, "source_type": {"const": "EXTERNAL_ESTIMATE"}})
    state_value = {
        "enum": [
            "observed",
            "estimated",
            "not_disclosed",
            "not_applicable",
            "not_evaluable",
            "conflicting_sources",
            "stale",
            "missing",
        ]
    }
    comp = {"enum": ["comparable", "partially_comparable", "not_comparable", "reference_only"]}
    score = {"type": "number", "minimum": 0, "maximum": 1}
    candidate_ids = {"type": "array", "items": STRING, "minItems": 1, "uniqueItems": True}
    assessment = closed(
        {
            "candidate_id": STRING,
            "score": score,
            "evidence_refs": {"type": "array", "items": STRING, "minItems": 1},
            "contrary_evidence_refs": {"type": "array", "items": STRING, "minItems": 1},
        }
    )
    scenario_case = closed(
        {
            "current_price": {"type": "number", "exclusiveMinimum": 0},
            "target_price": {"type": "number", "minimum": 0},
            "dividend": {"type": "number", "minimum": 0},
            "diluted_shares": {"type": "number", "exclusiveMinimum": 0},
            "realization_months": {"type": "number", "exclusiveMinimum": 0},
            "total_return": {"type": "number"},
            "annualized_return": {"type": "number"},
            "permanent_loss": {"type": "boolean"},
        }
    )
    scenario_result = closed(
        {
            "candidate_id": STRING,
            "scenarios": closed({name: scenario_case for name in SCENARIOS}),
            "probability_weighted_return": {"type": "number"},
            "probability_weighted_annualized_return": {"type": "number"},
            "expected_realization_months": {"type": "number", "exclusiveMinimum": 0},
            "downside_probability": score,
            "permanent_loss_probability": score,
        }
    )
    atomic_metric = closed(
        {
            "candidate_id": STRING,
            "ranking_type": {
                "enum": [
                    "company_quality",
                    "tactical",
                    "structural",
                    "risk_adjusted",
                    "portfolio_fit",
                ]
            },
            "value": score,
            "weight": {"type": "number", "minimum": 0},
            "effective_weight": {"type": "number", "minimum": 0},
            "applicable": {"type": "boolean"},
            "state": state_value,
            "comparability": comp,
            "dependency_root": STRING,
        }
    )
    handoff_ref = closed(
        {
            "handoff_id": STRING,
            "generation_id": STRING,
            "candidate_set_id": STRING,
            "status": {"enum": ["active", "superseded", "invalidated"]},
            "primary_candidate": {"type": ["string", "null"]},
            "secondary_candidate": {"type": ["string", "null"]},
            "conditional_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "watch_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "excluded_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "overall_decision": {"enum": ["SELECTION", "NO_SELECTION"]},
            "supersedes": {"type": ["string", "null"]},
        }
    )
    update_state = {
        "enum": ["changed", "unchanged", "added", "removed", "not_evaluable", "not_applicable"]
    }
    catalyst_state = {"enum": [*update_state["enum"], "no_identified_catalyst"]}
    string_change = closed(
        {"state": update_state, "values": {"type": "array", "items": STRING, "uniqueItems": True}}
    )
    valuation_change = closed(
        {
            "state": update_state,
            "data_state": state_value,
            "method": {"type": ["string", "null"]},
            "current_multiple": {"type": ["number", "null"]},
            "implied_growth": {"type": ["number", "null"]},
            "implied_margin": {"type": ["number", "null"]},
        }
    )
    candidate_context_change = closed(
        {
            "candidate_id": STRING,
            "valuation": valuation_change,
            "catalysts": closed(
                {
                    "state": catalyst_state,
                    "values": {"type": "array", "items": STRING, "uniqueItems": True},
                }
            ),
            "company_specific_risks": string_change,
            "thesis_invalidation_conditions": string_change,
            "confidence": closed(
                {
                    "state": update_state,
                    "value": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
                }
            ),
            "evidence_refs": string_change,
            "assumptions": string_change,
        }
    )
    phase_contracts = {
        1: (
            "session_and_candidates",
            closed(
                {
                    "theme": STRING,
                    "hypothesis": STRING,
                    "comparison_as_of": DT,
                    "source_cutoff_at": DT,
                    "candidate_inputs": {
                        "type": "array",
                        "items": candidate,
                        "minItems": 1,
                        "maxItems": 12,
                    },
                    "normalized_candidates": {
                        "type": "array",
                        "items": candidate,
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "candidate_set_id": STRING,
                    "data_state": state_value,
                    "latest_earnings_state": state_value,
                    "corporate_action_state": state_value,
                    "exclusions": {
                        "type": "array",
                        "items": closed({"candidate_id": STRING, "reason": STRING}),
                    },
                    "candidate_limits": closed(
                        {
                            "input": {"const": 12},
                            "phase1": {"const": 8},
                            "detail": {"const": 5},
                            "handoff": {"const": 2},
                        }
                    ),
                }
            ),
        ),
        2: (
            "business_models",
            closed(
                {
                    "candidates": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 5,
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "business_model_class": STRING,
                                "valuation_method": STRING,
                                "primary_metric": STRING,
                                "secondary_metric": STRING,
                                "capital_intensity": STRING,
                                "profitability_stage": STRING,
                                "maturity_stage": STRING,
                                "comparability_group": STRING,
                            }
                        ),
                    },
                    "comparability_matrix": {
                        "type": "array",
                        "minItems": 0,
                        "items": closed(
                            {
                                "left_candidate_id": STRING,
                                "right_candidate_id": STRING,
                                "metric": STRING,
                                "comparability": comp,
                            }
                        ),
                    },
                    "detailed_candidates": candidate_ids,
                }
            ),
        ),
        3: (
            "theme_value_capture",
            closed(
                {
                    "theme_purity": {"type": "array", "items": assessment, "minItems": 1},
                    "theme_sensitivity": {"type": "array", "items": assessment, "minItems": 1},
                    "value_capture": {"type": "array", "items": assessment, "minItems": 1},
                }
            ),
        ),
        4: (
            "competitive_structure",
            closed(
                {
                    "current_competitive_advantage": {
                        "type": "array",
                        "items": assessment,
                        "minItems": 1,
                    },
                    "future_competitive_advantage": {
                        "type": "array",
                        "items": assessment,
                        "minItems": 1,
                    },
                    "competitive_risks": {"type": "array", "items": STRING, "minItems": 1},
                }
            ),
        ),
        5: (
            "financial_conversion",
            closed(
                {
                    "conversion_paths": {
                        "type": "array",
                        "minItems": 1,
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "theme_demand": {"type": "number"},
                                "orders": {"type": "number"},
                                "revenue": {"type": "number"},
                                "gross_profit": {"type": "number"},
                                "operating_profit": {"type": "number"},
                                "free_cash_flow": {"type": "number"},
                                "diluted_per_share_value": {"type": "number"},
                            }
                        ),
                    },
                    "capital_structure_risks": {"type": "array", "items": STRING},
                }
            ),
        ),
        6: (
            "valuation_expectations",
            closed(
                {
                    "valuations": {
                        "type": "array",
                        "minItems": 1,
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "method": STRING,
                                "current_multiple": {"type": "number", "minimum": 0},
                                "implied_growth": {"type": "number"},
                                "implied_margin": {"type": "number"},
                                "bull_case_priced_in": {"type": "boolean"},
                                "evidence_refs": {"type": "array", "items": STRING, "minItems": 1},
                            }
                        ),
                    }
                }
            ),
        ),
        7: (
            "common_scenarios",
            closed(
                {
                    "probabilities": closed({name: score for name in SCENARIOS}),
                    "company_results": {"type": "array", "items": scenario_result, "minItems": 1},
                }
            ),
        ),
        8: (
            "catalysts",
            closed(
                {
                    "catalysts": {
                        "type": "array",
                        "minItems": 1,
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "status": {"enum": ["identified", "no_identified_catalyst"]},
                                "event": {"type": ["string", "null"]},
                                "expected_date": {
                                    "type": ["string", "null"],
                                    "format": "date-time",
                                },
                                "probability": {
                                    "type": ["number", "null"],
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "market_impact": {"type": ["string", "null"]},
                                "priced_in_level": {
                                    "type": ["number", "null"],
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                                "failure_impact": {"type": ["string", "null"]},
                                "evidence_refs": {"type": "array", "items": STRING},
                            }
                        ),
                    },
                    "rerating_paths": {
                        "type": "array",
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "months": {"enum": [3, 6, 12]},
                                "description": STRING,
                            }
                        ),
                    },
                }
            ),
        ),
        9: (
            "risks_and_stress",
            closed(
                {
                    "shared_theme_risks": {"type": "array", "items": STRING, "minItems": 1},
                    "company_risks": {
                        "type": "array",
                        "minItems": 1,
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "maximum_failure_path": STRING,
                                "thesis_invalidation_condition": STRING,
                                "financing_failure_path": STRING,
                                "dilution_path": STRING,
                                "survival_under_bear_case": {"type": "boolean"},
                            }
                        ),
                    },
                    "stress_tests": {"type": "array", "items": STRING, "minItems": 7},
                }
            ),
        ),
        10: (
            "final_selection",
            closed(
                {
                    "candidate_ids": candidate_ids,
                    "atomic_ranking_metrics": {
                        "type": "array",
                        "minItems": 1,
                        "items": atomic_metric,
                    },
                    "stored_rankings": closed(
                        {
                            name: candidate_ids
                            for name in [
                                "company_quality",
                                "tactical",
                                "structural",
                                "risk_adjusted",
                                "portfolio_fit",
                            ]
                        }
                    ),
                    "stored_scores": closed(
                        {
                            name: {"type": "object", "additionalProperties": {"type": "number"}}
                            for name in [
                                "company_quality",
                                "tactical",
                                "structural",
                                "risk_adjusted",
                                "portfolio_fit",
                            ]
                        }
                    ),
                    "scenario_probabilities": closed({name: score for name in SCENARIOS}),
                    "scenario_results": {"type": "array", "items": scenario_result, "minItems": 1},
                    "hard_gates": {
                        "type": "object",
                        "minProperties": 1,
                        "additionalProperties": {"type": "array", "items": STRING},
                    },
                    "classifications": {
                        "type": "array",
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "classification": {"enum": list(CLASSIFICATIONS)},
                            }
                        ),
                        "minItems": 1,
                    },
                    "overall_decision": {"enum": ["SELECTION", "NO_SELECTION"]},
                    "benchmark_inputs": closed(
                        {
                            "cash_annualized_return": {"type": "number"},
                            "investment_annualized_return": {"type": "number"},
                        }
                    ),
                    "risk_limits": closed(
                        {"max_downside_probability": score, "max_permanent_loss_probability": score}
                    ),
                    "handoff": handoff_ref,
                    "evidence_refs": {"type": "array", "items": STRING, "minItems": 1},
                }
            ),
        ),
        101: (
            "update_diff",
            closed(
                {
                    "old_generation": closed(
                        {
                            "generation_id": STRING,
                            "candidate_set_id": STRING,
                            "comparison_as_of": DT,
                            "source_cutoff_at": DT,
                        }
                    ),
                    "new_generation": closed(
                        {
                            "generation_id": STRING,
                            "candidate_set_id": STRING,
                            "comparison_as_of": DT,
                            "source_cutoff_at": DT,
                        }
                    ),
                    "changes": {
                        "type": "array",
                        "items": closed(
                            {"path": STRING, "before": {}, "after": {}, "change": STRING}
                        ),
                    },
                    "previous_detailed_candidates": candidate_ids,
                    "updated_detailed_candidates": candidate_ids,
                    "added_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                    "removed_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                    "retained_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                    "normalized_candidates": {
                        "type": "array",
                        "items": candidate,
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "updated_candidate_set_id": STRING,
                    "candidate_change_reasons": {
                        "type": "array",
                        "items": closed({"candidate_id": STRING, "reason": STRING}),
                    },
                    "handoff_context_changes": closed(
                        {
                            "candidate_changes": {
                                "type": "array",
                                "items": candidate_context_change,
                                "minItems": 1,
                            },
                            "shared_theme_risks": string_change,
                            "key_assumptions": string_change,
                        }
                    ),
                }
            ),
        ),
        102: (
            "updated_selection",
            closed(
                {
                    "ranking_changes": {
                        "type": "array",
                        "items": closed(
                            {
                                "candidate_id": STRING,
                                "before": {"type": "integer"},
                                "after": {"type": "integer"},
                            }
                        ),
                    },
                    "classification_changes": {
                        "type": "array",
                        "items": closed(
                            {"candidate_id": STRING, "before": STRING, "after": STRING}
                        ),
                    },
                    "superseded_handoff_id": STRING,
                    "updated_handoff": handoff_ref,
                }
            ),
        ),
    }
    update_selection_properties = {
        **phase_contracts[10][1]["properties"],
        "ranking_changes": phase_contracts[102][1]["properties"]["ranking_changes"],
        "classification_changes": phase_contracts[102][1]["properties"]["classification_changes"],
        "superseded_handoff_id": STRING,
        "updated_handoff": handoff_ref,
    }
    phase_contracts[102] = ("updated_selection", closed(update_selection_properties))
    variants = []
    for key, (field, phase_object) in phase_contracts.items():
        mode = "initial" if key < 100 else "update"
        phase = key if key < 100 else key - 100
        payload = closed({field: phase_object, "summary": STRING})
        variants.append(
            closed(
                {
                    "mode": {"const": mode},
                    "phase": {"const": phase},
                    "generation_id": STRING,
                    "candidate_set_id": STRING,
                    "source_cutoff_at": DT,
                    "facts": {"type": "array", "items": fact},
                    "company_claims": {"type": "array", "items": claim},
                    "external_estimates": {"type": "array", "items": estimate},
                    "judgments": {"type": "array", "items": judgment},
                    "payload": payload,
                }
            )
        )
    artifact = {"$schema": "https://json-schema.org/draft/2020-12/schema", "oneOf": variants}
    confidence_snapshot = closed(
        {
            "state": {"enum": ["observed", "estimated", "not_evaluable", "not_applicable"]},
            "value": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
        }
    )
    confidence_snapshot["allOf"] = [
        {
            "if": {"properties": {"state": {"enum": ["observed", "estimated"]}}},
            "then": {"properties": {"value": {"enum": ["low", "medium", "high"]}}},
            "else": {"properties": {"value": {"type": "null"}}},
        }
    ]
    catalyst_snapshot = closed(
        {
            "state": {
                "enum": [
                    "identified",
                    "no_identified_catalyst",
                    "not_evaluable",
                    "not_applicable",
                ]
            },
            "values": {"type": "array", "items": STRING, "uniqueItems": True},
        }
    )
    catalyst_snapshot["allOf"] = [
        {
            "if": {"properties": {"state": {"const": "identified"}}},
            "then": {"properties": {"values": {"minItems": 1}}},
            "else": {"properties": {"values": {"maxItems": 0}}},
        }
    ]
    analysis_list_snapshot = closed(
        {
            "state": {"enum": ["observed", "not_evaluable", "not_applicable"]},
            "values": {"type": "array", "items": STRING, "uniqueItems": True},
        }
    )
    analysis_list_snapshot["allOf"] = [
        {
            "if": {"properties": {"state": {"enum": ["not_evaluable", "not_applicable"]}}},
            "then": {"properties": {"values": {"maxItems": 0}}},
        }
    ]
    handoff = closed(
        {
            "schema_version": STRING,
            "handoff_id": STRING,
            "session_id": STRING,
            "generation_id": STRING,
            "candidate_set_id": STRING,
            "theme": STRING,
            "comparison_as_of": DT,
            "source_cutoff_at": DT,
            "created_at": DT,
            "status": {"enum": ["active", "superseded", "invalidated"]},
            "supersedes": {"type": ["string", "null"]},
            "superseded_by": {"type": ["string", "null"]},
            "invalidated_at": {"type": ["string", "null"], "format": "date-time"},
            "invalidation_reason": {"type": ["string", "null"]},
            "investment_horizon": closed(
                {"tactical": {"const": "6-12 months"}, "structural": {"const": "2-3 years"}}
            ),
            "primary_candidate": {"type": ["string", "null"]},
            "secondary_candidate": {"type": ["string", "null"]},
            "conditional_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "watch_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "excluded_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "overall_decision": {"enum": ["SELECTION", "NO_SELECTION"]},
            "ranking_by_horizon": closed(
                {
                    name: candidate_ids
                    for name in [
                        "company_quality",
                        "tactical",
                        "structural",
                        "risk_adjusted",
                        "portfolio_fit",
                    ]
                }
            ),
            "common_scenarios": closed({name: score for name in SCENARIOS}),
            "company_scenario_results": {"type": "object", "additionalProperties": scenario_result},
            "key_assumptions": {"type": "array", "items": STRING},
            "candidate_assumptions": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": STRING, "uniqueItems": True},
            },
            "shared_theme_risks": {"type": "array", "items": STRING},
            "company_specific_risks": {
                "type": "object",
                "additionalProperties": analysis_list_snapshot,
            },
            "catalysts": {
                "type": "object",
                "additionalProperties": catalyst_snapshot,
            },
            "valuation_ranges": {
                "type": "object",
                "additionalProperties": closed(
                    {
                        "state": state_value,
                        "method": {"type": ["string", "null"]},
                        "current_multiple": {"type": ["number", "null"]},
                        "implied_growth": {"type": ["number", "null"]},
                        "implied_margin": {"type": ["number", "null"]},
                    }
                ),
            },
            "thesis_invalidation_conditions": {
                "type": "object",
                "additionalProperties": analysis_list_snapshot,
            },
            "confidence": {
                "type": "object",
                "additionalProperties": confidence_snapshot,
            },
            "global_evidence_refs": {"type": "array", "items": STRING, "uniqueItems": True},
            "candidate_evidence_refs": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": STRING, "uniqueItems": True},
            },
            "evidence_manifest": {"type": "array", "items": STRING},
            "recommended_next_action": STRING,
        }
    )
    history_item = closed(
        {
            "candidate_set_id": STRING,
            "comparison_as_of": DT,
            "source_cutoff_at": DT,
            "detailed_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
            "artifacts": {"type": "array", "items": artifact},
        }
    )
    state = closed(
        {
            "mode": {"enum": ["initial", "update"]},
            "session_id": STRING,
            "generation_id": STRING,
            "active_generation_id": STRING,
            "initial_generation_id": STRING,
            "previous_generation_id": {"type": ["string", "null"]},
            "generation_history": {"type": "object", "additionalProperties": history_item},
            "candidate_set_id": STRING,
            "comparison_as_of": DT,
            "source_cutoff_at": DT,
            "current_phase": {"type": "integer", "minimum": 1, "maximum": 10},
            "completed_phases": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 10},
                "uniqueItems": True,
            },
            "status": {"enum": ["in_progress", "complete", "failed_terminal"]},
            "persistence_status": {"enum": list(PERSISTENCE)},
            "handoff_history": {"type": "object", "additionalProperties": handoff},
            "active_handoff_id": {"type": ["string", "null"]},
            "superseded_handoff_ids": {"type": "array", "items": STRING, "uniqueItems": True},
        }
    )
    inventory = closed(
        {
            "path": STRING,
            "raw_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "size": {"type": "integer", "minimum": 1, "maximum": 48000},
            "sequence": {"type": "integer", "minimum": 1},
            "part_count": {"type": "integer", "minimum": 1},
            "generation_id": STRING,
        }
    )
    schemas = {
        "candidate-input": closed(
            {
                "theme": STRING,
                "candidates": {"type": "array", "minItems": 1, "maxItems": 12, "items": candidate},
            }
        ),
        "normalized-candidate": candidate,
        "session-state": state,
        "phase-artifact": artifact,
        "common-scenario": closed(
            {x: {"type": "number", "minimum": 0, "maximum": 1} for x in SCENARIOS}
        ),
        "ranking": closed(
            {
                "ordered_candidates": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": STRING},
                },
                "scores": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                },
                "metrics": {"type": "array"},
            }
        ),
        "final-selection": closed(
            {
                "classifications": {
                    "type": "array",
                    "items": closed(
                        {"candidate_id": STRING, "classification": {"enum": list(CLASSIFICATIONS)}}
                    ),
                },
                "overall_decision": {"enum": ["SELECTION", "NO_SELECTION"]},
                "hard_gates": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": STRING},
                },
            }
        ),
        "handoff": handoff,
        "publication-manifest": closed(
            {
                "schema_version": STRING,
                "generation_id": STRING,
                "candidate_set_id": STRING,
                "source_cutoff_at": DT,
                "created_at": DT,
                "inventory": {"type": "array", "minItems": 1, "items": inventory},
                "canonical_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "verification_status": {"enum": list(PERSISTENCE)},
                "failure_reason": {"type": ["string", "null"]},
                "failed_at": {"type": ["string", "null"], "format": "date-time"},
                "failed_stage": {"type": ["string", "null"]},
            },
            [
                "schema_version",
                "generation_id",
                "candidate_set_id",
                "source_cutoff_at",
                "created_at",
                "inventory",
                "canonical_sha256",
                "verification_status",
            ],
        ),
        "update-diff": closed(
            {
                "old_generation_id": STRING,
                "new_generation_id": STRING,
                "changes": {
                    "type": "array",
                    "items": closed(
                        {
                            "path": STRING,
                            "before": {},
                            "after": {},
                            "change": {
                                "enum": [
                                    "added",
                                    "removed",
                                    "changed",
                                    "classification_changed",
                                    "ranking_changed",
                                    "evidence_added",
                                    "evidence_removed",
                                    "assumption_changed",
                                    "invalidation_triggered",
                                    "comparability_changed",
                                    "candidate_added",
                                    "candidate_removed",
                                ]
                            },
                        }
                    ),
                },
                "invalidated_handoff": STRING,
            }
        ),
        "update-start": closed(
            {
                "new_generation_id": STRING,
                "new_candidate_set_id": STRING,
                "new_comparison_as_of": DT,
                "new_source_cutoff_at": DT,
                "previous_generation_id": STRING,
            }
        ),
    }
    target = ROOT / "src" / "theme_compare" / "schemas"
    target.mkdir(exist_ok=True)
    for name, schema in schemas.items():
        schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
        (target / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
