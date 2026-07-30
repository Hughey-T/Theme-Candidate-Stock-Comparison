"""Persisted state machine: no conversational or hidden-memory state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import INITIAL_PHASES, UPDATE_PHASES
from .models import SemanticError, parse_rfc3339, strict_json_loads
from .schema_runtime import validate_document
from .phase_validation import validate_phase_artifact
from .validation import validate_envelope


class StateMachine:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        raw = self.path.read_bytes()
        state: dict[str, Any] = strict_json_loads(raw)
        validate_document("session-state", state)
        if state["generation_id"] != state["active_generation_id"]:
            raise SemanticError("active generation mismatch")
        artifacts = state["generation_history"][state["active_generation_id"]]["artifacts"]
        validate_envelope(
            {**state, "generation_id": state["active_generation_id"], "artifacts": artifacts}
        )
        self._validate_state_semantics(state)
        self._validate_generation_history(state)
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
            if state["mode"] == "initial" and phase == 10:
                self._activate_initial_handoff(state, artifact["payload"]["final_selection"])
            elif state["mode"] == "update" and phase == 2:
                self._apply_update_handoff(state, artifact["payload"]["updated_selection"])
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

    def _handoff_from_selection(
        self, state: dict[str, Any], reference: dict[str, Any], selection: dict[str, Any]
    ) -> dict[str, Any]:
        by_class = {
            name: [
                row["candidate_id"]
                for row in selection.get("classifications", [])
                if row["classification"] == name
            ]
            for name in ("PRIMARY", "SECONDARY", "CONDITIONAL", "WATCH", "EXCLUDED")
        }
        theme = state["generation_history"][state["initial_generation_id"]]["artifacts"][0][
            "payload"
        ]["session_and_candidates"]["theme"]
        candidates = selection.get("candidate_ids", [])
        return {
            "schema_version": "1.0.0",
            "handoff_id": reference["handoff_id"],
            "session_id": state["session_id"],
            "generation_id": state["active_generation_id"],
            "candidate_set_id": state["candidate_set_id"],
            "theme": theme,
            "comparison_as_of": state["comparison_as_of"],
            "source_cutoff_at": state["source_cutoff_at"],
            "created_at": state["source_cutoff_at"],
            "status": "active",
            "supersedes": reference.get("supersedes"),
            "superseded_by": None,
            "invalidated_at": None,
            "invalidation_reason": None,
            "investment_horizon": {"tactical": "6-12 months", "structural": "2-3 years"},
            "primary_candidate": by_class["PRIMARY"][0]
            if by_class["PRIMARY"]
            else reference.get("primary_candidate"),
            "secondary_candidate": by_class["SECONDARY"][0]
            if by_class["SECONDARY"]
            else reference.get("secondary_candidate"),
            "conditional_candidates": by_class["CONDITIONAL"],
            "watch_candidates": by_class["WATCH"],
            "excluded_candidates": by_class["EXCLUDED"],
            "overall_decision": reference["overall_decision"],
            "ranking_by_horizon": selection.get("stored_rankings", {}),
            "common_scenarios": selection.get("scenario_probabilities", {}),
            "company_scenario_results": {
                row["candidate_id"]: row for row in selection.get("scenario_results", [])
            },
            "key_assumptions": [],
            "shared_theme_risks": [],
            "company_specific_risks": {candidate: [] for candidate in candidates},
            "catalysts": {candidate: [] for candidate in candidates},
            "valuation_ranges": {candidate: {"low": 0.0, "high": 0.0} for candidate in candidates},
            "thesis_invalidation_conditions": {candidate: [] for candidate in candidates},
            "confidence": {candidate: "low" for candidate in candidates},
            "evidence_manifest": [],
            "recommended_next_action": "個別株完全分析"
            if reference["overall_decision"] == "SELECTION"
            else "NO_SELECTION",
        }

    def _activate_initial_handoff(self, state: dict[str, Any], selection: dict[str, Any]) -> None:
        handoff = self._handoff_from_selection(state, selection["handoff"], selection)
        state["handoff_history"][handoff["handoff_id"]] = handoff
        state["active_handoff_id"] = handoff["handoff_id"]

    def _apply_update_handoff(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        old_id = state["active_handoff_id"]
        if old_id is None or payload["superseded_handoff_id"] != old_id:
            raise SemanticError("active handoff required for update")
        reference = payload["updated_handoff"]
        if (
            reference.get("supersedes") != old_id
            or reference["generation_id"] != state["active_generation_id"]
        ):
            raise SemanticError("updated handoff lineage mismatch")
        new_handoff = self._handoff_from_selection(state, reference, payload)
        old = state["handoff_history"][old_id]
        old.update(
            status="superseded",
            superseded_by=new_handoff["handoff_id"],
            invalidated_at=state["source_cutoff_at"],
            invalidation_reason="update generation",
        )
        state["handoff_history"][new_handoff["handoff_id"]] = new_handoff
        state["active_handoff_id"] = new_handoff["handoff_id"]
        state["superseded_handoff_ids"] = list(
            dict.fromkeys([*state["superseded_handoff_ids"], old_id])
        )

    def _validate_state_semantics(self, state: dict[str, Any]) -> None:
        entry = state["generation_history"][state["active_generation_id"]]
        if (
            entry["comparison_as_of"] != state["comparison_as_of"]
            or entry["source_cutoff_at"] != state["source_cutoff_at"]
        ):
            raise SemanticError("active generation timestamp mismatch")
        if parse_rfc3339(state["source_cutoff_at"]) > parse_rfc3339(state["comparison_as_of"]):
            raise SemanticError("future source cutoff")
        for handoff in state["handoff_history"].values():
            candidates = set().union(
                *(
                    set(handoff[key])
                    for key in ("conditional_candidates", "watch_candidates", "excluded_candidates")
                ),
                {
                    candidate
                    for candidate in (handoff["primary_candidate"], handoff["secondary_candidate"])
                    if candidate
                },
            )
            for key in (
                "company_scenario_results",
                "company_specific_risks",
                "catalysts",
                "valuation_ranges",
                "thesis_invalidation_conditions",
                "confidence",
            ):
                if set(handoff[key]) != candidates:
                    raise SemanticError(f"handoff {key} candidate coverage mismatch")
            if any(
                candidate != result["candidate_id"]
                for candidate, result in handoff["company_scenario_results"].items()
            ):
                raise SemanticError("handoff scenario map identity mismatch")
            for ranking in handoff["ranking_by_horizon"].values():
                if len(ranking) != len(set(ranking)) or set(ranking) != candidates:
                    raise SemanticError("handoff ranking candidate coverage mismatch")

    def _validate_generation_history(self, state: dict[str, Any]) -> None:
        for generation_id, entry in state["generation_history"].items():
            if parse_rfc3339(entry["source_cutoff_at"]) > parse_rfc3339(entry["comparison_as_of"]):
                raise SemanticError("generation history future cutoff")
            expected_mode = (
                "initial" if generation_id == state["initial_generation_id"] else "update"
            )
            temporary = {
                **state,
                "active_generation_id": generation_id,
                "generation_id": generation_id,
                "candidate_set_id": entry["candidate_set_id"],
                "comparison_as_of": entry["comparison_as_of"],
                "source_cutoff_at": entry["source_cutoff_at"],
                "generation_history": {
                    **state["generation_history"],
                    generation_id: {**entry, "artifacts": []},
                },
            }
            for expected_phase, artifact in enumerate(entry["artifacts"], 1):
                validate_document("phase-artifact", artifact)
                if artifact["mode"] != expected_mode or artifact["phase"] != expected_phase:
                    raise SemanticError("generation history phase sequence mismatch")
                validate_envelope(
                    {**temporary, "generation_id": generation_id, "artifacts": [artifact]}
                )
                if expected_mode == "initial":
                    validate_phase_artifact(temporary, artifact)
                temporary["generation_history"][generation_id]["artifacts"].append(artifact)
