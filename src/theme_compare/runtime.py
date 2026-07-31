"""Application service coordinating validation, generations, and persistence."""

from __future__ import annotations

import json
import uuid
from typing import Any

from .models import SemanticError, candidate_set_id, canonical_bytes, parse_rfc3339
from .phase_validation import validate_update_candidate_partition
from .schema_runtime import schema_bytes, validate_document
from .storage import JsonVolumeStorage
from .validation import validate_candidates

_PHASE_REQUIREMENTS = {
    "initial": {
        i: text
        for i, text in enumerate(
            (
                "",
                "Fix bootstrap identities and select at most eight candidates.",
                "Classify business models and select detailed candidates.",
                "Assess theme value capture.",
                "Assess competitive structure.",
                "Model financial conversion.",
                "Assess valuation expectations.",
                "Calculate common scenarios.",
                "Assess catalysts.",
                "Assess risks and stress paths.",
                "Recalculate ranking and typed handoff.",
            )
        )
        if i
    },
    "update": {
        1: "Produce the complete persisted old/new generation diff.",
        2: "Re-rank and supersede the active typed handoff.",
    },
}


def _identity_map(rows: list[dict[str, Any]]) -> dict[str, bytes]:
    return {row["candidate_id"]: canonical_bytes(row) for row in rows}


def phase_schema(mode: str, phase: int) -> dict[str, Any]:
    """Return exactly one generated closed schema branch, without copying its vocabulary."""
    schema = json.loads(schema_bytes("phase-artifact"))
    matches = [
        branch
        for branch in schema["oneOf"]
        if branch["properties"]["mode"].get("const") == mode
        and branch["properties"]["phase"].get("const") == phase
    ]
    if len(matches) != 1:
        raise RuntimeError("generated phase schema branch is missing or ambiguous")
    selected: dict[str, Any] = matches[0]
    selected["$schema"] = schema["$schema"]
    return selected


class RuntimeIntegrityError(RuntimeError):
    """A terminal protocol-integrity error."""


class RuntimeService:
    def __init__(self, storage: JsonVolumeStorage) -> None:
        self.storage = storage

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("schema_version") not in (None, "1.0.0"):
            raise RuntimeIntegrityError("unsupported upstream Schema version")
        validate_document("upstream-theme-handoff", body)
        comparison = parse_rfc3339(body["comparison_as_of"])
        if parse_rfc3339(body["source_cutoff_at"]) > comparison:
            raise SemanticError("source cutoff must not be after comparison as-of")
        upstream_id = candidate_set_id(body["candidate_inputs"])
        validate_candidates(body["candidate_inputs"], upstream_id)
        session_id = "s_" + uuid.uuid4().hex
        context = {
            "schema_version": body["schema_version"],
            "theme": body["theme"],
            "hypothesis": body["hypothesis"],
            "source_session_id": body["source_session_id"],
            "source_generation_id": body["source_generation_id"],
            "evidence_refs": body["evidence_refs"],
            "upstream_candidate_set_id": upstream_id,
            "candidate_inputs": body["candidate_inputs"],
            "generation_contexts": {
                "g1": {
                    "candidate_inputs": body["candidate_inputs"],
                    "candidate_set_id": upstream_id,
                }
            },
        }
        state = {
            "mode": "initial",
            "session_id": session_id,
            "generation_id": "g1",
            "active_generation_id": "g1",
            "initial_generation_id": "g1",
            "previous_generation_id": None,
            "generation_history": {
                "g1": {
                    "candidate_set_id": upstream_id,
                    "comparison_as_of": body["comparison_as_of"],
                    "source_cutoff_at": body["source_cutoff_at"],
                    "detailed_candidates": [],
                    "artifacts": [],
                }
            },
            "candidate_set_id": upstream_id,
            "comparison_as_of": body["comparison_as_of"],
            "source_cutoff_at": body["source_cutoff_at"],
            "current_phase": 1,
            "completed_phases": [],
            "status": "in_progress",
            "persistence_status": "integrity_verified",
            "handoff_history": {},
            "active_handoff_id": None,
            "superseded_handoff_ids": [],
            "runtime_context": context,
        }
        self.storage.create(session_id, state)
        return {
            "session_id": session_id,
            "generation_id": "g1",
            "upstream_candidate_set_id": upstream_id,
            "analysis_candidate_set_id": None,
            "next_phase": 1,
            "next_contract": self.contract(session_id),
        }

    def summary(self, session_id: str) -> dict[str, Any]:
        state = self.storage.load(session_id)
        context = state["runtime_context"]
        return {
            "session_id": session_id,
            **{
                key: state[key]
                for key in (
                    "mode",
                    "status",
                    "current_phase",
                    "completed_phases",
                    "active_generation_id",
                    "candidate_set_id",
                    "comparison_as_of",
                    "source_cutoff_at",
                    "persistence_status",
                )
            },
            "upstream_candidate_set_id": context["upstream_candidate_set_id"],
            "analysis_candidate_set_id": context.get("analysis_candidate_set_id"),
            "source_lineage": self._lineage(context),
            "next_allowed_operation": self._next(state),
        }

    def contract(self, session_id: str) -> dict[str, Any]:
        state = self.storage.load(session_id)
        if state["status"] == "complete":
            raise SemanticError("generation complete; next operation is 更新")
        phase = state["current_phase"]
        context = state["runtime_context"]
        generation = state["active_generation_id"]
        coverage = state["generation_history"][generation]["detailed_candidates"]
        bootstrap: dict[str, Any] | None = None
        if state["mode"] == "initial" and phase == 1:
            coverage = [row["candidate_id"] for row in context["candidate_inputs"]]
            bootstrap = {
                key: context[key]
                for key in (
                    "schema_version",
                    "theme",
                    "hypothesis",
                    "source_session_id",
                    "source_generation_id",
                    "evidence_refs",
                    "upstream_candidate_set_id",
                    "candidate_inputs",
                )
            }
        elif state["mode"] == "update" and phase == 1:
            previous = state["previous_generation_id"]
            bootstrap = {
                "previous_generation": self._generation(state, previous),
                "new_generation": self._generation(state, generation),
                "previous_detailed_candidates": state["generation_history"][previous][
                    "detailed_candidates"
                ],
                "new_candidate_inputs": context["generation_contexts"][generation][
                    "candidate_inputs"
                ],
                "new_candidate_set_id": context["generation_contexts"][generation][
                    "candidate_set_id"
                ],
                "previous_active_handoff": state["handoff_history"].get(state["active_handoff_id"]),
                "source_lineage": self._lineage(context),
            }
            coverage = [row["candidate_id"] for row in bootstrap["new_candidate_inputs"]]
        return {
            "mode": state["mode"],
            "phase": phase,
            "artifact_schema": phase_schema(state["mode"], phase),
            "phase_requirements": _PHASE_REQUIREMENTS[state["mode"]][phase],
            "required_candidate_coverage": coverage,
            "generation_metadata": self._generation(state, generation),
            "source_cutoff_at": state["source_cutoff_at"],
            "source_lineage": self._lineage(context),
            "bootstrap": bootstrap,
        }

    def submit(self, session_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            nonlocal result
            completed = state["current_phase"]
            if state["mode"] == "initial" and completed == 1:
                self._validate_initial_phase1(state, artifact)
            elif state["mode"] == "update" and completed == 1:
                self._validate_update_phase1(state, artifact)
            try:
                transitioned = self.storage.transition(state, "次", artifact)
            except SemanticError as exc:
                if "mixed-generation" in str(exc) or "mixed generation" in str(exc):
                    raise RuntimeIntegrityError(str(exc)) from exc
                raise
            active = (
                transitioned["handoff_history"].get(transitioned["active_handoff_id"])
                if transitioned["active_handoff_id"]
                else None
            )
            result = {
                "accepted": True,
                "mode": transitioned["mode"],
                "completed_phase": completed,
                "status": transitioned["status"],
                "next_phase": None
                if transitioned["status"] == "complete"
                else transitioned["current_phase"],
                "next_allowed_operation": self._next(transitioned),
                "display_summary": f"{transitioned['mode']} Phase {completed} accepted",
                "active_handoff": active,
            }
            return transitioned, result

        return self.storage.transaction(session_id, mutate)

    def update(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        expected = {"new_comparison_as_of", "new_source_cutoff_at", "candidate_inputs"}
        if set(body) != expected:
            raise SemanticError(f"request properties must be exactly {sorted(expected)}")
        validate_document(
            "candidate-input", {"theme": "update", "candidates": body["candidate_inputs"]}
        )
        set_id = candidate_set_id(body["candidate_inputs"])
        validate_candidates(body["candidate_inputs"], set_id)
        result: dict[str, Any] = {}

        def mutate(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            nonlocal result
            old_id = state["active_generation_id"]
            generation = f"g{max(int(key[1:]) for key in state['generation_history']) + 1}"
            transitioned = self.storage.transition(
                state,
                "更新",
                {
                    "new_generation_id": generation,
                    "new_candidate_set_id": set_id,
                    "new_comparison_as_of": body["new_comparison_as_of"],
                    "new_source_cutoff_at": body["new_source_cutoff_at"],
                    "previous_generation_id": old_id,
                },
            )
            transitioned["runtime_context"]["generation_contexts"][generation] = {
                "candidate_inputs": body["candidate_inputs"],
                "candidate_set_id": set_id,
            }
            result = {
                "session_id": session_id,
                "old_generation": self._generation(state, old_id),
                "new_generation": self._generation(transitioned, generation),
                "source_lineage": self._lineage(state["runtime_context"]),
                "next_phase": 1,
            }
            return transitioned, result

        return self.storage.transaction(session_id, mutate)

    def handoff(self, session_id: str, history: bool = False) -> dict[str, Any]:
        state = self.storage.load(session_id)
        if state["active_handoff_id"] is None:
            raise SemanticError("active handoff is not available")
        result = {
            "active_handoff": state["handoff_history"][state["active_handoff_id"]],
            "source_lineage": self._lineage(state["runtime_context"]),
        }
        if history:
            result["handoff_history"] = list(state["handoff_history"].values())
        return result

    def _validate_initial_phase1(self, state: dict[str, Any], artifact: dict[str, Any]) -> None:
        payload = artifact.get("payload", {}).get("session_and_candidates", {})
        context = state["runtime_context"]
        for key, expected in (
            ("source_session_id", context["source_session_id"]),
            ("source_generation_id", context["source_generation_id"]),
            ("upstream_evidence_refs", context["evidence_refs"]),
            ("theme", context["theme"]),
            ("hypothesis", context["hypothesis"]),
            ("comparison_as_of", state["comparison_as_of"]),
            ("source_cutoff_at", state["source_cutoff_at"]),
        ):
            if payload.get(key) != expected:
                raise SemanticError(f"Phase 1 bootstrap mismatch: {key}")
        upstream = _identity_map(context["candidate_inputs"])
        supplied = _identity_map(payload.get("candidate_inputs", []))
        normalized = _identity_map(payload.get("normalized_candidates", []))
        if supplied != upstream:
            raise SemanticError("Phase 1 candidate_inputs mismatch persisted upstream identities")
        if (
            not normalized
            or len(normalized) > 8
            or any(upstream.get(key) != value for key, value in normalized.items())
        ):
            raise SemanticError(
                "normalized_candidates must be a 1..8 identity-preserving upstream subset"
            )
        excluded = [row.get("candidate_id") for row in payload.get("exclusions", [])]
        if len(excluded) != len(set(excluded)) or set(excluded) != set(upstream) - set(normalized):
            raise SemanticError(
                "Phase 1 exclusions must exactly equal the upstream/analysis difference"
            )
        analysis_id = candidate_set_id(payload["normalized_candidates"])
        if (
            payload.get("candidate_set_id") != analysis_id
            or artifact.get("candidate_set_id") != analysis_id
        ):
            raise SemanticError("Phase 1 analysis candidate-set ID mismatch")
        state["candidate_set_id"] = analysis_id
        state["generation_history"]["g1"]["candidate_set_id"] = analysis_id
        context["analysis_candidate_set_id"] = analysis_id
        context["generation_contexts"]["g1"]["analysis_candidate_set_id"] = analysis_id

    def _validate_update_phase1(self, state: dict[str, Any], artifact: dict[str, Any]) -> None:
        diff = artifact.get("payload", {}).get("update_diff", {})
        generation = state["active_generation_id"]
        previous = state["previous_generation_id"]
        expected_rows = state["runtime_context"]["generation_contexts"][generation][
            "candidate_inputs"
        ]
        if _identity_map(diff.get("normalized_candidates", [])) != _identity_map(expected_rows):
            raise SemanticError(
                "update normalized_candidates mismatch persisted generation context"
            )
        expected_new = candidate_set_id(expected_rows)
        if (
            diff.get("updated_candidate_set_id") != expected_new
            or artifact.get("candidate_set_id") != expected_new
        ):
            raise SemanticError("update candidate-set ID mismatch")
        previous_detailed = state["generation_history"][previous]["detailed_candidates"]
        validate_update_candidate_partition(previous_detailed, diff)

    @staticmethod
    def _generation(state: dict[str, Any], generation: str) -> dict[str, Any]:
        item = state["generation_history"][generation]
        return {
            "generation_id": generation,
            "candidate_set_id": item["candidate_set_id"],
            "comparison_as_of": item["comparison_as_of"],
            "source_cutoff_at": item["source_cutoff_at"],
        }

    @staticmethod
    def _lineage(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_session_id": context["source_session_id"],
            "source_generation_id": context["source_generation_id"],
            "evidence_refs": context["evidence_refs"],
        }

    @staticmethod
    def _next(state: dict[str, Any]) -> str:
        return "更新" if state["status"] == "complete" else "次"
