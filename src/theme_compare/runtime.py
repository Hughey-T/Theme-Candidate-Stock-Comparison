"""Application service coordinating validation, generations, and persistence."""

from __future__ import annotations

import json
import uuid
from typing import Any

from .models import SemanticError, candidate_set_id, parse_rfc3339
from .schema_runtime import schema_bytes, validate_document
from .state import StateMachine
from .storage import JsonVolumeStorage
from .validation import validate_candidates

_PHASE_REQUIREMENTS = {
    "initial": {
        1: "Fix session, hypothesis, normalized identities, as-of and cutoff.",
        2: "Classify business models and choose at most five detailed candidates.",
        3: "Assess theme purity, sensitivity, and value capture.",
        4: "Assess competitive structure without price.",
        5: "Model demand-to-diluted-per-share conversion.",
        6: "Assess business-model-specific valuation expectations.",
        7: "Calculate all candidates under common bear/base/bull scenarios.",
        8: "Assess dated catalysts and 3/6/12-month paths.",
        9: "Assess shared/company risks and stress paths.",
        10: "Recalculate ranking, selection, and typed handoff (maximum two).",
    },
    "update": {
        1: "Produce the complete old/new generation diff.",
        2: "Re-rank and supersede the active typed handoff.",
    },
}


class RuntimeService:
    def __init__(self, storage: JsonVolumeStorage) -> None:
        self.storage = storage

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        self._closed(
            body,
            {"theme", "hypothesis", "comparison_as_of", "source_cutoff_at", "candidate_inputs"},
        )
        validate_document(
            "candidate-input", {"theme": body["theme"], "candidates": body["candidate_inputs"]}
        )
        parse_rfc3339(body["comparison_as_of"])
        if parse_rfc3339(body["source_cutoff_at"]) > parse_rfc3339(body["comparison_as_of"]):
            raise SemanticError("source cutoff must not be after comparison as-of")
        set_id = candidate_set_id(body["candidate_inputs"])
        validate_candidates(body["candidate_inputs"], set_id)
        session_id = "s_" + uuid.uuid4().hex
        state = {
            "mode": "initial",
            "session_id": session_id,
            "generation_id": "g1",
            "active_generation_id": "g1",
            "initial_generation_id": "g1",
            "previous_generation_id": None,
            "generation_history": {
                "g1": {
                    "candidate_set_id": set_id,
                    "comparison_as_of": body["comparison_as_of"],
                    "source_cutoff_at": body["source_cutoff_at"],
                    "detailed_candidates": [],
                    "artifacts": [],
                }
            },
            "candidate_set_id": set_id,
            "comparison_as_of": body["comparison_as_of"],
            "source_cutoff_at": body["source_cutoff_at"],
            "current_phase": 1,
            "completed_phases": [],
            "status": "in_progress",
            "persistence_status": "integrity_verified",
            "handoff_history": {},
            "active_handoff_id": None,
            "superseded_handoff_ids": [],
            "runtime_context": {
                "theme": body["theme"],
                "hypothesis": body["hypothesis"],
                "candidate_inputs": body["candidate_inputs"],
            },
        }
        self.storage.create(session_id, state)
        return {
            "session_id": session_id,
            "generation_id": "g1",
            "candidate_set_id": set_id,
            "next_phase": 1,
            "next_contract": self.contract(session_id),
        }

    def summary(self, session_id: str) -> dict[str, Any]:
        state = self.storage.load(session_id)
        keys = (
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
        return {
            **{key: state[key] for key in keys},
            "session_id": session_id,
            "next_allowed_operation": self._next(state),
        }

    def contract(self, session_id: str) -> dict[str, Any]:
        state = self.storage.load(session_id)
        if state["status"] == "complete":
            raise SemanticError("generation complete; next operation is 更新")
        phase = state["current_phase"]
        coverage = state["generation_history"][state["active_generation_id"]]["detailed_candidates"]
        if state["mode"] == "initial" and phase == 1:
            coverage = [
                row["candidate_id"]
                for row in state.get("runtime_context", {}).get("candidate_inputs", [])
            ]
        return {
            "mode": state["mode"],
            "phase": phase,
            "artifact_schema": json.loads(schema_bytes("phase-artifact")),
            "phase_requirements": _PHASE_REQUIREMENTS[state["mode"]][phase],
            "required_candidate_coverage": coverage,
            "generation_metadata": {
                "session_id": session_id,
                "generation_id": state["active_generation_id"],
                "candidate_set_id": state["candidate_set_id"],
                "comparison_as_of": state["comparison_as_of"],
            },
            "source_cutoff_at": state["source_cutoff_at"],
            "bootstrap": state.get("runtime_context")
            if state["mode"] == "initial" and phase == 1
            else None,
        }

    def submit(self, session_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
        with self.storage.locked(session_id):
            before = self.storage.load(session_id)
            completed = before["current_phase"]
            state = StateMachine(self.storage.path(session_id)).command("次", artifact)
        active = (
            state["handoff_history"].get(state["active_handoff_id"])
            if state["active_handoff_id"]
            else None
        )
        return {
            "accepted": True,
            "mode": state["mode"],
            "completed_phase": completed,
            "status": state["status"],
            "next_phase": None if state["status"] == "complete" else state["current_phase"],
            "next_allowed_operation": self._next(state),
            "display_summary": f"{state['mode']} Phase {completed} accepted",
            "active_handoff": active,
        }

    def update(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._closed(body, {"new_comparison_as_of", "new_source_cutoff_at", "candidate_inputs"})
        with self.storage.locked(session_id):
            old = self.storage.load(session_id)
            validate_document(
                "candidate-input",
                {
                    "theme": old.get("runtime_context", {}).get("theme", "update"),
                    "candidates": body["candidate_inputs"],
                },
            )
            set_id = candidate_set_id(body["candidate_inputs"])
            validate_candidates(body["candidate_inputs"], set_id)
            generation = f"g{max(int(key[1:]) for key in old['generation_history']) + 1}"
            state = StateMachine(self.storage.path(session_id)).command(
                "更新",
                {
                    "new_generation_id": generation,
                    "new_candidate_set_id": set_id,
                    "new_comparison_as_of": body["new_comparison_as_of"],
                    "new_source_cutoff_at": body["new_source_cutoff_at"],
                    "previous_generation_id": old["active_generation_id"],
                },
            )
        return {
            "session_id": session_id,
            "old_generation": {
                "generation_id": old["active_generation_id"],
                "candidate_set_id": old["candidate_set_id"],
            },
            "new_generation": {
                "generation_id": generation,
                "candidate_set_id": set_id,
                "comparison_as_of": state["comparison_as_of"],
                "source_cutoff_at": state["source_cutoff_at"],
            },
            "next_phase": 1,
        }

    def handoff(self, session_id: str, history: bool = False) -> dict[str, Any]:
        state = self.storage.load(session_id)
        if state["active_handoff_id"] is None:
            raise SemanticError("active handoff is not available")
        result = {"active_handoff": state["handoff_history"][state["active_handoff_id"]]}
        if history:
            result["handoff_history"] = list(state["handoff_history"].values())
        return result

    @staticmethod
    def _closed(body: dict[str, Any], expected: set[str]) -> None:
        if set(body) != expected:
            raise SemanticError(f"request properties must be exactly {sorted(expected)}")

    @staticmethod
    def _next(state: dict[str, Any]) -> str:
        return "更新" if state["status"] == "complete" else "次"
