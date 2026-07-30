"""Generate closed JSON Schemas from the canonical constants."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]

STRING = {"type": "string", "minLength": 1}
DATETIME = {"type": "string", "format": "date-time", "pattern": r"(Z|[+-]\d\d:\d\d)$"}


def closed(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required or list(properties),
    }


def main() -> None:
    from theme_compare.constants import (
        CLASSIFICATIONS,
        COMPARABILITY,
        HARD_GATES,
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
    schemas = {
        "candidate-input": closed(
            {
                "theme": STRING,
                "candidates": {"type": "array", "minItems": 1, "maxItems": 12, "items": candidate},
            }
        ),
        "normalized-candidate": candidate,
        "session-state": closed(
            {
                "mode": {"enum": ["initial", "update"]},
                "session_id": STRING,
                "generation_id": STRING,
                "candidate_set_id": STRING,
                "comparison_as_of": DATETIME,
                "source_cutoff_at": DATETIME,
                "current_phase": {"type": "integer", "minimum": 1, "maximum": 10},
                "completed_phases": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 10},
                    "uniqueItems": True,
                },
                "status": {"enum": ["in_progress", "complete", "failed_terminal"]},
                "persistence_status": {"enum": list(PERSISTENCE)},
                "artifacts": {"type": "array"},
            }
        ),
        "phase-artifact": closed(
            {
                "phase": {"type": "integer", "minimum": 1, "maximum": 10},
                "generation_id": STRING,
                "candidate_set_id": STRING,
                "source_cutoff_at": DATETIME,
                "facts": {"type": "array"},
                "company_claims": {"type": "array"},
                "external_estimates": {"type": "array"},
                "judgments": {"type": "array"},
                "payload": {"type": "object"},
            }
        ),
        "common-scenario": closed(
            {name: {"type": "number", "minimum": 0, "maximum": 1} for name in SCENARIOS}
        ),
        "ranking": closed(
            {
                "ranking_type": {
                    "enum": [
                        "company_quality",
                        "tactical",
                        "structural",
                        "risk_adjusted",
                        "portfolio_fit",
                    ]
                },
                "ordered_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                "comparability": {"enum": list(COMPARABILITY)},
            }
        ),
        "final-selection": closed(
            {
                "candidate_id": STRING,
                "classification": {"enum": list(CLASSIFICATIONS)},
                "hard_gates": {
                    "type": "array",
                    "items": {"enum": list(HARD_GATES)},
                    "uniqueItems": True,
                },
                "reason": STRING,
                "contrary_evidence_refs": {"type": "array", "items": STRING, "minItems": 1},
            }
        ),
        "handoff": closed(
            {
                "schema_version": STRING,
                "session_id": STRING,
                "generation_id": STRING,
                "candidate_set_id": STRING,
                "theme": STRING,
                "comparison_as_of": DATETIME,
                "source_cutoff_at": DATETIME,
                "investment_horizon": closed(
                    {"tactical": {"const": "6-12 months"}, "structural": {"const": "2-3 years"}}
                ),
                "primary_candidate": {"type": ["string", "null"]},
                "secondary_candidate": {"type": ["string", "null"]},
                "conditional_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                "watch_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                "excluded_candidates": {"type": "array", "items": STRING, "uniqueItems": True},
                "no_selection": {"type": "boolean"},
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
        ),
        "publication-manifest": closed(
            {
                "schema_version": STRING,
                "generation_id": STRING,
                "candidate_set_id": STRING,
                "source_cutoff_at": DATETIME,
                "created_at": DATETIME,
                "inventory": {"type": "array", "minItems": 1},
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
                        {"field": STRING, "before": {}, "after": {}, "change": {"const": "changed"}}
                    ),
                },
                "invalidated_handoff": STRING,
            }
        ),
    }
    target = ROOT / "schemas"
    target.mkdir(exist_ok=True)
    for name, schema in schemas.items():
        (target / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
