"""Canonical vocabulary: schemas, code and instructions import this module."""

SCHEMA_VERSION = "2.0.0"
# v1 remains readable by the legacy service.  New sessions use this preferred
# contract; an in-flight v1 generation is deliberately never guessed forward.
PREVIOUS_SCHEMA_VERSION = "1.0.0"
# Legacy v1 engine constants (read-only compatibility path).
INITIAL_PHASES = 10
UPDATE_PHASES = 2
V2_INITIAL_PHASES = 12
V2_UPDATE_PHASES = 4
MAX_INPUT = 12
MAX_PHASE1 = 8
MAX_DETAIL = 5
MAX_HANDOFF = 2
MAX_PART_BYTES = 48_000
DATA_STATES = (
    "observed",
    "estimated",
    "not_disclosed",
    "not_applicable",
    "not_evaluable",
    "conflicting_sources",
    "stale",
    "missing",
)
COMPARABILITY = (
    "directly_comparable",
    "comparable_after_normalization",
    "directionally_comparable",
    "not_comparable",
    "not_applicable",
    "insufficient_evidence",
)
CLASSIFICATIONS = ("PRIMARY", "SECONDARY", "CONDITIONAL", "WATCH", "EXCLUDED")
OVERALL_DECISIONS = ("SELECTION", "NO_SELECTION")
PERSISTENCE = (
    "not_generated",
    "generated_not_persisted",
    "persisted_pending_verification",
    "integrity_verified",
    "failed_terminal",
    "superseded",
)
SCENARIOS = ("THEME_BEAR", "THEME_BASE", "THEME_BULL")
HARD_GATES = (
    "weak_theme_link",
    "unreliable_financials",
    "insufficient_verifiability",
    "going_concern",
    "unclear_liquidity",
    "major_dilution",
    "illiquid",
    "unevaluable_share_structure",
    "bull_case_priced_in",
    "clear_competitive_disadvantage",
    "thesis_already_invalidated",
    "portfolio_loss_policy_breach",
)
