"""Persisted state machine: no conversational or hidden-memory state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import INITIAL_PHASES, UPDATE_PHASES
from .models import SemanticError, parse_rfc3339
from .schema_runtime import validate_document
from .phase_validation import validate_phase_artifact
from .validation import validate_envelope


class StateMachine:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        raw = self.path.read_bytes()
        state: dict[str, Any] = json.loads(raw)
        validate_document("session-state", state)
        if state["generation_id"] != state["active_generation_id"]:
            raise SemanticError("active generation mismatch")
        artifacts = state["generation_history"][state["active_generation_id"]]["artifacts"]
        validate_envelope(
            {**state, "generation_id": state["active_generation_id"], "artifacts": artifacts}
        )
        self._validate_state_semantics(state)
        stop = state["current_phase"] + (1 if state["status"] == "complete" else 0)
        expected = list(range(1, stop))
        if state["completed_phases"] != expected:
            raise SemanticError("invalid phase history")
        maximum = INITIAL_PHASES if state["mode"] == "initial" else UPDATE_PHASES
        if not 1 <= state["current_phase"] <= maximum:
            raise SemanticError("invalid current phase")
        return state

    def command(self, operation: str, artifact: dict[str, Any] | None = None) -> dict[str, Any]:
        if operation not in {"次", "更新"}:
            raise SemanticError("only 次 and 更新 are accepted")
        state = self.load()
        if operation == "更新":
            if state["mode"] != "initial" or state["status"] != "complete":
                raise SemanticError("update requires completed initial analysis")
            if artifact is None:
                raise SemanticError("update metadata required")
            validate_document("update-start", artifact)
            if artifact["previous_generation_id"] != state["active_generation_id"]:
                raise SemanticError("previous generation mismatch")
            if artifact["new_generation_id"] == state["active_generation_id"]:
                raise SemanticError("update requires a new generation")
            new_comparison = parse_rfc3339(artifact["new_comparison_as_of"])
            new_cutoff = parse_rfc3339(artifact["new_source_cutoff_at"])
            if new_cutoff > new_comparison or new_comparison < parse_rfc3339(
                state["comparison_as_of"]
            ):
                raise SemanticError("invalid update timestamps")
            if artifact["new_source_cutoff_at"] == state["source_cutoff_at"]:
                raise SemanticError("update must not silently reuse stale cutoff")
            previous = state["active_generation_id"]
            new_generation = artifact["new_generation_id"]
            state.update(
                mode="update",
                generation_id=new_generation,
                active_generation_id=new_generation,
                previous_generation_id=previous,
                candidate_set_id=artifact["new_candidate_set_id"],
                comparison_as_of=artifact["new_comparison_as_of"],
                source_cutoff_at=artifact["new_source_cutoff_at"],
                current_phase=1,
                completed_phases=[],
                status="in_progress",
            )
            state["generation_history"][new_generation] = {
                "candidate_set_id": artifact["new_candidate_set_id"],
                "comparison_as_of": artifact["new_comparison_as_of"],
                "source_cutoff_at": artifact["new_source_cutoff_at"],
                "artifacts": [],
            }
        else:
            if state["status"] == "complete":
                raise SemanticError("analysis is already complete")
            phase = state["current_phase"]
            if artifact is None or artifact["phase"] != phase:
                raise SemanticError("phase skip, replay, or wrong artifact")
            if artifact["mode"] != state["mode"]:
                raise SemanticError("artifact mode does not match state")
            validate_document("phase-artifact", artifact)
            validate_phase_artifact(state, artifact)
            validate_envelope(
                {**state, "generation_id": state["active_generation_id"], "artifacts": [artifact]}
            )
            state["generation_history"][state["active_generation_id"]]["artifacts"].append(artifact)
            state["completed_phases"].append(phase)
            maximum = INITIAL_PHASES if state["mode"] == "initial" else UPDATE_PHASES
            if phase == maximum:
                state["status"] = "complete"
            else:
                state["current_phase"] += 1
        validate_document("session-state", state)
        self._validate_state_semantics(state)
        self._atomic_write(state)
        return state

    def _atomic_write(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(self.path)

    def _validate_state_semantics(self, state: dict[str, Any]) -> None:
        entry = state["generation_history"][state["active_generation_id"]]
        if (
            entry["comparison_as_of"] != state["comparison_as_of"]
            or entry["source_cutoff_at"] != state["source_cutoff_at"]
        ):
            raise SemanticError("active generation timestamp mismatch")
        if parse_rfc3339(state["source_cutoff_at"]) > parse_rfc3339(state["comparison_as_of"]):
            raise SemanticError("future source cutoff")

    def supersede_handoff(self, old_id: str, new_handoff: dict[str, Any]) -> None:
        state = self.load()
        validate_document("handoff", new_handoff)
        if state["active_handoff_id"] != old_id or new_handoff["supersedes"] != old_id:
            raise SemanticError("handoff supersession mismatch")
        old = state["handoff_history"][old_id]
        old.update(
            status="superseded",
            superseded_by=new_handoff["handoff_id"],
            invalidated_at=new_handoff["created_at"],
            invalidation_reason="update generation",
        )
        state["handoff_history"][new_handoff["handoff_id"]] = new_handoff
        state["superseded_handoff_ids"].append(old_id)
        state["active_handoff_id"] = new_handoff["handoff_id"]
        self._atomic_write(state)
