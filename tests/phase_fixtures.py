from theme_compare.models import candidate_set_id
from theme_compare.ranking import RANKING_TYPES

CANDIDATE = {
    "candidate_id": "A",
    "issuer_id": "issuer-A",
    "issuer_name": "Issuer A",
    "ticker": "AAA",
    "exchange": "XNAS",
    "share_class": "common",
    "is_adr": False,
    "underlying_security_id": None,
    "former_tickers": [],
    "corporate_action_lineage": [],
    "listing_country": "US",
}
CANDIDATE_B = {
    **CANDIDATE,
    "candidate_id": "B",
    "issuer_id": "issuer-B",
    "issuer_name": "Issuer B",
    "ticker": "BBB",
}
SET_ID = candidate_set_id([CANDIDATE, CANDIDATE_B])
TS = "2025-01-01T00:00:00Z"


def scenario_case(target=110.0):
    total = (target + 1) / 100 - 1
    return {
        "current_price": 100.0,
        "target_price": target,
        "dividend": 1.0,
        "diluted_shares": 10.0,
        "realization_months": 12.0,
        "total_return": total,
        "annualized_return": total,
        "permanent_loss": False,
    }


def scenario_result():
    cases = {
        "THEME_BEAR": scenario_case(80),
        "THEME_BASE": scenario_case(110),
        "THEME_BULL": scenario_case(140),
    }
    probs = {"THEME_BEAR": 0.2, "THEME_BASE": 0.5, "THEME_BULL": 0.3}
    returns = {k: v["total_return"] for k, v in cases.items()}
    expected = sum(probs[k] * returns[k] for k in probs)
    return {
        "candidate_id": "A",
        "scenarios": cases,
        "probability_weighted_return": expected,
        "probability_weighted_annualized_return": expected,
        "expected_realization_months": 12.0,
        "downside_probability": 0.2,
        "permanent_loss_probability": 0.0,
    }


def phase_object(phase, mode="initial"):
    assessment = {
        "candidate_id": "A",
        "score": 0.7,
        "evidence_refs": ["E1"],
        "contrary_evidence_refs": ["E2"],
    }
    if mode == "update":
        if phase == 1:
            return "update_diff", {
                "old_generation": {
                    "generation_id": "g1",
                    "candidate_set_id": SET_ID,
                    "comparison_as_of": TS,
                    "source_cutoff_at": TS,
                },
                "new_generation": {
                    "generation_id": "g2",
                    "candidate_set_id": SET_ID,
                    "comparison_as_of": "2025-02-01T00:00:00Z",
                    "source_cutoff_at": "2025-01-31T00:00:00Z",
                },
                "changes": [],
            }
        return "updated_selection", {
            "ranking_changes": [],
            "classification_changes": [],
            "superseded_handoff_id": "h1",
            "updated_handoff": {
                "handoff_id": "h2",
                "generation_id": "g2",
                "status": "active",
                "primary_candidate": "A",
                "secondary_candidate": None,
                "overall_decision": "SELECTION",
            },
        }
    if phase == 1:
        return "session_and_candidates", {
            "theme": "AI",
            "hypothesis": "growth",
            "comparison_as_of": TS,
            "source_cutoff_at": TS,
            "candidate_inputs": [CANDIDATE, CANDIDATE_B],
            "normalized_candidates": [CANDIDATE, CANDIDATE_B],
            "candidate_set_id": SET_ID,
            "data_state": "observed",
            "latest_earnings_state": "observed",
            "corporate_action_state": "observed",
            "exclusions": [],
            "candidate_limits": {"input": 12, "phase1": 8, "detail": 5, "handoff": 2},
        }
    if phase == 2:
        return "business_models", {
            "candidates": [
                {
                    "candidate_id": "A",
                    "business_model_class": "software",
                    "valuation_method": "DCF",
                    "primary_metric": "FCF",
                    "secondary_metric": "revenue",
                    "capital_intensity": "low",
                    "profitability_stage": "profitable",
                    "maturity_stage": "growth",
                    "comparability_group": "g1",
                },
                {
                    "candidate_id": "B",
                    "business_model_class": "hardware",
                    "valuation_method": "DCF",
                    "primary_metric": "FCF",
                    "secondary_metric": "revenue",
                    "capital_intensity": "high",
                    "profitability_stage": "profitable",
                    "maturity_stage": "growth",
                    "comparability_group": "g1",
                },
            ],
            "comparability_matrix": [
                {
                    "left_candidate_id": "A",
                    "right_candidate_id": "B",
                    "metric": "revenue",
                    "comparability": "reference_only",
                }
            ],
            "detailed_candidates": ["A", "B"],
        }
    if phase == 3:
        return "theme_value_capture", {
            "theme_purity": [assessment],
            "theme_sensitivity": [assessment],
            "value_capture": [assessment],
        }
    if phase == 4:
        return "competitive_structure", {
            "current_competitive_advantage": [assessment],
            "future_competitive_advantage": [assessment],
            "competitive_risks": ["competition"],
        }
    if phase == 5:
        return "financial_conversion", {
            "conversion_paths": [
                {
                    "candidate_id": "A",
                    "theme_demand": 1,
                    "orders": 1,
                    "revenue": 1,
                    "gross_profit": 1,
                    "operating_profit": 1,
                    "free_cash_flow": 1,
                    "diluted_per_share_value": 1,
                }
            ],
            "capital_structure_risks": [],
        }
    if phase == 6:
        return "valuation_expectations", {
            "valuations": [
                {
                    "candidate_id": "A",
                    "method": "DCF",
                    "current_multiple": 10,
                    "implied_growth": 0.2,
                    "implied_margin": 0.2,
                    "bull_case_priced_in": False,
                    "evidence_refs": ["E1"],
                }
            ]
        }
    if phase == 7:
        return "common_scenarios", {
            "probabilities": {"THEME_BEAR": 0.2, "THEME_BASE": 0.5, "THEME_BULL": 0.3},
            "company_results": [scenario_result()],
        }
    if phase == 8:
        return "catalysts", {
            "catalysts": [
                {
                    "candidate_id": "A",
                    "event": "earnings",
                    "expected_date": "2025-02-01T00:00:00Z",
                    "probability": 0.5,
                    "market_impact": "medium",
                    "priced_in_level": 0.5,
                    "failure_impact": "downside",
                    "evidence_refs": ["E1"],
                }
            ],
            "rerating_paths": [],
        }
    if phase == 9:
        return "risks_and_stress", {
            "shared_theme_risks": ["rates"],
            "company_risks": [
                {
                    "candidate_id": "A",
                    "maximum_failure_path": "loss",
                    "thesis_invalidation_condition": "demand",
                    "financing_failure_path": "none",
                    "dilution_path": "none",
                    "survival_under_bear_case": True,
                }
            ],
            "stress_tests": [str(x) for x in range(7)],
        }
    metrics = [
        {
            "candidate_id": "A",
            "ranking_type": name,
            "value": 0.8,
            "weight": 1.0,
            "effective_weight": 1.0,
            "applicable": True,
            "state": "observed",
            "comparability": "comparable",
            "dependency_root": name,
        }
        for name in RANKING_TYPES
    ]
    orders = {name: ["A"] for name in RANKING_TYPES}
    scores = {name: {"A": 0.8} for name in RANKING_TYPES}
    return "final_selection", {
        "candidate_ids": ["A"],
        "atomic_ranking_metrics": metrics,
        "stored_rankings": orders,
        "stored_scores": scores,
        "scenario_probabilities": {"THEME_BEAR": 0.2, "THEME_BASE": 0.5, "THEME_BULL": 0.3},
        "scenario_results": [scenario_result()],
        "hard_gates": {"A": []},
        "classifications": [{"candidate_id": "A", "classification": "PRIMARY"}],
        "overall_decision": "SELECTION",
        "benchmark_inputs": {"cash_annualized_return": 0.02, "investment_annualized_return": 0.03},
        "risk_limits": {"max_downside_probability": 0.5, "max_permanent_loss_probability": 0.2},
        "handoff": {
            "handoff_id": "h1",
            "generation_id": "g1",
            "status": "active",
            "primary_candidate": "A",
            "secondary_candidate": None,
            "overall_decision": "SELECTION",
        },
        "evidence_refs": ["E1"],
    }


def artifact(phase, generation="g1", mode="initial", cutoff=TS):
    field, value = phase_object(phase, mode)
    evidence = [
        {"evidence_id": "E1", "statement": "support", "source_type": "FACT", "as_of": cutoff},
        {"evidence_id": "E2", "statement": "contrary", "source_type": "FACT", "as_of": cutoff},
    ]
    return {
        "mode": mode,
        "phase": phase,
        "generation_id": generation,
        "candidate_set_id": SET_ID,
        "source_cutoff_at": cutoff,
        "facts": evidence,
        "company_claims": [],
        "external_estimates": [],
        "judgments": [
            {
                "judgment": "j",
                "evidence_refs": ["E1"],
                "contrary_evidence_refs": ["E2"],
                "confidence": "medium",
                "assumptions": [],
                "invalidation_conditions": ["x"],
            }
        ],
        "payload": {field: value, "summary": "complete"},
    }
