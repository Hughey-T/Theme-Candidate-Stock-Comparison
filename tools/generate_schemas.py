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

    evidence = closed(
        {
            "evidence_id": STRING,
            "statement": STRING,
            "source_type": {"enum": ["FACT", "COMPANY_CLAIM", "EXTERNAL_ESTIMATE"]},
            "as_of": DT,
        }
    )
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
    phase_fields = {
        1: "session_and_candidates",
        2: "business_models",
        3: "theme_value_capture",
        4: "competitive_structure",
        5: "financial_conversion",
        6: "valuation_expectations",
        7: "common_scenarios",
        8: "catalysts",
        9: "risks_and_stress",
        10: "final_selection",
        101: "update_diff",
        102: "updated_selection",
    }
    variants = []
    for key, field in phase_fields.items():
        mode = "initial" if key < 100 else "update"
        phase = key if key < 100 else key - 100
        payload = closed({field: {"type": "object"}, "summary": STRING})
        variants.append(
            closed(
                {
                    "mode": {"const": mode},
                    "phase": {"const": phase},
                    "generation_id": STRING,
                    "candidate_set_id": STRING,
                    "source_cutoff_at": DT,
                    "facts": {"type": "array", "items": evidence},
                    "company_claims": {"type": "array", "items": evidence},
                    "external_estimates": {"type": "array", "items": evidence},
                    "judgments": {"type": "array", "items": judgment},
                    "payload": payload,
                }
            )
        )
    artifact = {"$schema": "https://json-schema.org/draft/2020-12/schema", "oneOf": variants}
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
            "ranking_by_horizon": {"type": "object"},
            "common_scenarios": {"type": "object"},
            "company_scenario_results": {"type": "object"},
            "key_assumptions": {"type": "array"},
            "shared_theme_risks": {"type": "array"},
            "company_specific_risks": {"type": "object"},
            "catalysts": {"type": "object"},
            "valuation_ranges": {"type": "object"},
            "thesis_invalidation_conditions": {"type": "object"},
            "confidence": {"type": "object"},
            "evidence_manifest": {"type": "array"},
            "recommended_next_action": STRING,
        }
    )
    history_item = closed(
        {"candidate_set_id": STRING, "artifacts": {"type": "array", "items": artifact}}
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
                "ordered_candidates": {"type": "object"},
                "scores": {"type": "object"},
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
                "hard_gates": {"type": "object"},
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
            }
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
    }
    target = ROOT / "schemas"
    target.mkdir(exist_ok=True)
    for name, schema in schemas.items():
        schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
        (target / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
