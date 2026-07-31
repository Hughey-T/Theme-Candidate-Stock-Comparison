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
            if state["status"] != "complete":
                raise SemanticError("update requires a completed generation")
            if artifact is None:
                raise SemanticError("update metadata required")
            validate_document("update-start", artifact)
            if artifact["previous_generation_id"] != state["active_generation_id"]:
                raise SemanticError("previous generation mismatch")
            if artifact["new_generation_id"] in state["generation_history"]:
                raise SemanticError("update requires a new generation")
            new_comparison = parse_rfc3339(artifact["new_comparison_as_of"])
            new_cutoff = parse_rfc3339(artifact["new_source_cutoff_at"])
            previous_comparison = parse_rfc3339(state["comparison_as_of"])
            previous_cutoff = parse_rfc3339(state["source_cutoff_at"])
            if new_cutoff > new_comparison:
                raise SemanticError("invalid update timestamps")
            if new_comparison < previous_comparison or new_cutoff <= previous_cutoff:
                raise SemanticError("update timestamps must advance monotonically")
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
                "detailed_candidates": [],
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
            if state["mode"] == "initial" and phase == 2:
                state["generation_history"][state["active_generation_id"]][
                    "detailed_candidates"
                ] = artifact["payload"]["business_models"]["detailed_candidates"]
            elif state["mode"] == "update" and phase == 1:
                state["generation_history"][state["active_generation_id"]][
                    "detailed_candidates"
                ] = artifact["payload"]["update_diff"]["updated_detailed_candidates"]
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
        projected = self._project_handoff_context(state, candidates)
        return {
            "schema_version": "2.0.0",
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
            "overall_decision": selection["overall_decision"],
            "ranking_by_horizon": selection.get("stored_rankings", {}),
            "common_scenarios": selection.get("scenario_probabilities", {}),
            "company_scenario_results": {
                row["candidate_id"]: row for row in selection.get("scenario_results", [])
            },
            **projected,
            "recommended_next_action": "個別株完全分析"
            if selection["overall_decision"] == "SELECTION"
            else "NO_SELECTION",
        }

    def _project_handoff_context(
        self, state: dict[str, Any], candidates: list[str]
    ) -> dict[str, Any]:
        if state["mode"] == "update" and state["active_handoff_id"] is not None:
            previous = state["handoff_history"][state["active_handoff_id"]]
            projected: dict[str, Any] = {
                "key_assumptions": list(previous["key_assumptions"]),
                "candidate_assumptions": {
                    candidate: list(previous["candidate_assumptions"].get(candidate, []))
                    for candidate in candidates
                },
                "shared_theme_risks": list(previous["shared_theme_risks"]),
                "company_specific_risks": {
                    candidate: previous["company_specific_risks"].get(
                        candidate, {"state": "not_evaluable", "values": []}
                    )
                    for candidate in candidates
                },
                "catalysts": {
                    candidate: previous["catalysts"].get(
                        candidate, {"state": "not_evaluable", "values": []}
                    )
                    for candidate in candidates
                },
                "valuation_ranges": {
                    candidate: previous["valuation_ranges"].get(
                        candidate,
                        {
                            "state": "not_evaluable",
                            "method": None,
                            "current_multiple": None,
                            "implied_growth": None,
                            "implied_margin": None,
                        },
                    )
                    for candidate in candidates
                },
                "thesis_invalidation_conditions": {
                    candidate: previous["thesis_invalidation_conditions"].get(
                        candidate, {"state": "not_evaluable", "values": []}
                    )
                    for candidate in candidates
                },
                "confidence": {
                    candidate: previous["confidence"].get(
                        candidate, {"state": "not_evaluable", "value": None}
                    )
                    for candidate in candidates
                },
                "global_evidence_refs": list(previous["global_evidence_refs"]),
                "candidate_evidence_refs": {
                    candidate: list(previous["candidate_evidence_refs"].get(candidate, []))
                    for candidate in candidates
                },
            }
            update_artifact = state["generation_history"][state["active_generation_id"]][
                "artifacts"
            ][0]
            changes = update_artifact["payload"]["update_diff"]["handoff_context_changes"]

            def changed(item: dict[str, Any]) -> bool:
                return bool(item["state"] != "unchanged")

            for candidate_change in sorted(
                changes["candidate_changes"], key=lambda item: item["candidate_id"]
            ):
                candidate = candidate_change["candidate_id"]
                if candidate not in candidates:
                    continue
                valuation = candidate_change["valuation"]
                if changed(valuation):
                    unavailable = valuation["state"] in (
                        "removed",
                        "not_evaluable",
                        "not_applicable",
                    )
                    snapshot_state = (
                        "not_evaluable" if valuation["state"] == "removed" else valuation["state"]
                    )
                    projected["valuation_ranges"][candidate] = {
                        "state": snapshot_state if unavailable else valuation["data_state"],
                        "method": None if unavailable else valuation["method"],
                        "current_multiple": None if unavailable else valuation["current_multiple"],
                        "implied_growth": None if unavailable else valuation["implied_growth"],
                        "implied_margin": None if unavailable else valuation["implied_margin"],
                    }
                for source, target in (
                    ("company_specific_risks", "company_specific_risks"),
                    ("thesis_invalidation_conditions", "thesis_invalidation_conditions"),
                ):
                    item = candidate_change[source]
                    if changed(item):
                        state_value = item["state"]
                        projected[target][candidate] = {
                            "state": state_value
                            if state_value in ("not_evaluable", "not_applicable")
                            else "not_evaluable"
                            if state_value == "removed"
                            else "observed",
                            "values": []
                            if state_value in ("removed", "not_evaluable", "not_applicable")
                            else item["values"],
                        }
                catalyst = candidate_change["catalysts"]
                if changed(catalyst):
                    operation = catalyst["state"]
                    snapshot_state = "not_evaluable" if operation == "removed" else operation
                    if snapshot_state in ("changed", "added"):
                        snapshot_state = "identified"
                    projected["catalysts"][candidate] = {
                        "state": snapshot_state,
                        "values": catalyst["values"] if snapshot_state == "identified" else [],
                    }
                confidence = candidate_change["confidence"]
                if changed(confidence):
                    operation = confidence["state"]
                    unavailable = operation in ("removed", "not_evaluable", "not_applicable")
                    projected["confidence"][candidate] = {
                        "state": "not_evaluable"
                        if operation == "removed"
                        else operation
                        if unavailable
                        else "observed",
                        "value": None if unavailable else confidence["value"],
                    }
            if changed(changes["shared_theme_risks"]):
                projected["shared_theme_risks"] = changes["shared_theme_risks"]["values"]
            if changed(changes["key_assumptions"]):
                projected["key_assumptions"] = changes["key_assumptions"]["values"]
            for candidate_change in sorted(
                changes["candidate_changes"], key=lambda item: item["candidate_id"]
            ):
                candidate = candidate_change["candidate_id"]
                assumptions = candidate_change["assumptions"]
                if assumptions["state"] == "changed":
                    projected["candidate_assumptions"][candidate] = assumptions["values"]
                elif assumptions["state"] == "added":
                    projected["candidate_assumptions"][candidate] = sorted(
                        set(projected["candidate_assumptions"][candidate])
                        | set(assumptions["values"])
                    )
                elif assumptions["state"] == "removed":
                    projected["candidate_assumptions"][candidate] = [
                        value
                        for value in projected["candidate_assumptions"][candidate]
                        if value not in assumptions["values"]
                    ]
                evidence = candidate_change["evidence_refs"]
                if evidence["state"] == "changed":
                    projected["candidate_evidence_refs"][candidate] = evidence["values"]
                elif evidence["state"] == "added":
                    projected["candidate_evidence_refs"][candidate] = sorted(
                        set(projected["candidate_evidence_refs"][candidate])
                        | set(evidence["values"])
                    )
                elif evidence["state"] == "removed":
                    projected["candidate_evidence_refs"][candidate] = [
                        value
                        for value in projected["candidate_evidence_refs"][candidate]
                        if value not in evidence["values"]
                    ]
            projected["evidence_manifest"] = sorted(
                set(projected["global_evidence_refs"])
                | {
                    evidence
                    for candidate in sorted(projected["candidate_evidence_refs"])
                    for evidence in projected["candidate_evidence_refs"][candidate]
                }
            )
            return projected
        artifacts = state["generation_history"][state["initial_generation_id"]]["artifacts"]
        valuations = {
            row["candidate_id"]: row
            for row in artifacts[5]["payload"]["valuation_expectations"]["valuations"]
        }
        catalyst_rows = {
            row["candidate_id"]: row for row in artifacts[7]["payload"]["catalysts"]["catalysts"]
        }
        risks = artifacts[8]["payload"]["risks_and_stress"]
        risk_rows = {row["candidate_id"]: row for row in risks["company_risks"]}
        assumptions = sorted(
            {
                assumption
                for artifact in artifacts
                for judgment in artifact["judgments"]
                for assumption in judgment["assumptions"]
            }
        )
        evidence = [
            item
            for artifact in artifacts
            for collection in ("facts", "company_claims", "external_estimates")
            for item in artifact[collection]
        ]
        global_evidence_refs = sorted(
            {item["evidence_id"] for item in evidence if item["candidate_id"] is None}
        )
        candidate_evidence_refs = {
            candidate: sorted(
                {item["evidence_id"] for item in evidence if item["candidate_id"] == candidate}
            )
            for candidate in candidates
        }
        confidence_value = next(
            (
                judgment["confidence"]
                for artifact in reversed(artifacts)
                for judgment in artifact["judgments"]
            ),
            "low",
        )
        return {
            "key_assumptions": assumptions,
            "candidate_assumptions": {candidate: [] for candidate in candidates},
            "shared_theme_risks": risks["shared_theme_risks"],
            "company_specific_risks": {
                candidate: {
                    "state": "observed",
                    "values": list(
                        dict.fromkeys(
                            risk_rows[candidate][key]
                            for key in (
                                "maximum_failure_path",
                                "financing_failure_path",
                                "dilution_path",
                            )
                        )
                    ),
                }
                for candidate in candidates
            },
            "catalysts": {
                candidate: {
                    "state": catalyst_rows[candidate]["status"],
                    "values": [catalyst_rows[candidate]["event"]]
                    if catalyst_rows[candidate]["status"] == "identified"
                    else [],
                }
                for candidate in candidates
            },
            "valuation_ranges": {
                candidate: {
                    "state": "observed",
                    "method": valuations[candidate]["method"],
                    "current_multiple": valuations[candidate]["current_multiple"],
                    "implied_growth": valuations[candidate]["implied_growth"],
                    "implied_margin": valuations[candidate]["implied_margin"],
                }
                for candidate in candidates
            },
            "thesis_invalidation_conditions": {
                candidate: {
                    "state": "observed",
                    "values": [risk_rows[candidate]["thesis_invalidation_condition"]],
                }
                for candidate in candidates
            },
            "confidence": {
                candidate: {"state": "observed", "value": confidence_value}
                for candidate in candidates
            },
            "global_evidence_refs": global_evidence_refs,
            "candidate_evidence_refs": candidate_evidence_refs,
            "evidence_manifest": sorted(
                set(global_evidence_refs)
                | {
                    evidence_id
                    for candidate in sorted(candidate_evidence_refs)
                    for evidence_id in candidate_evidence_refs[candidate]
                }
            ),
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
            handoff_cutoff = parse_rfc3339(handoff["source_cutoff_at"])
            evidence_registry: dict[str, dict[str, Any]] = {}
            for generation in state["generation_history"].values():
                if parse_rfc3339(generation["source_cutoff_at"]) > handoff_cutoff:
                    continue
                for artifact in generation["artifacts"]:
                    for collection in ("facts", "company_claims", "external_estimates"):
                        for evidence in artifact[collection]:
                            evidence_id = evidence["evidence_id"]
                            if evidence_id in evidence_registry:
                                raise SemanticError("duplicate evidence ID in handoff registry")
                            if parse_rfc3339(evidence["as_of"]) > handoff_cutoff:
                                raise SemanticError("handoff references future evidence")
                            evidence_registry[evidence_id] = evidence
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
                "candidate_assumptions",
                "candidate_evidence_refs",
            ):
                if set(handoff[key]) != candidates:
                    raise SemanticError(f"handoff {key} candidate coverage mismatch")
            for candidate in candidates:
                confidence = handoff["confidence"][candidate]
                if (confidence["state"] in ("observed", "estimated")) != (
                    confidence["value"] is not None
                ):
                    raise SemanticError("handoff confidence state/value mismatch")
                catalyst = handoff["catalysts"][candidate]
                if (catalyst["state"] == "identified") != bool(catalyst["values"]):
                    raise SemanticError("handoff catalyst state/value mismatch")
                for field in (
                    "company_specific_risks",
                    "thesis_invalidation_conditions",
                ):
                    snapshot = handoff[field][candidate]
                    if snapshot["state"] != "observed" and snapshot["values"]:
                        raise SemanticError(f"handoff {field} unavailable state has values")
                valuation = handoff["valuation_ranges"][candidate]
                if valuation["state"] in ("not_evaluable", "not_applicable") and any(
                    valuation[field] is not None
                    for field in ("method", "current_multiple", "implied_growth", "implied_margin")
                ):
                    raise SemanticError("handoff valuation unavailable state has values")
                if valuation["state"] in ("observed", "estimated") and all(
                    valuation[field] is None
                    for field in ("method", "current_multiple", "implied_growth", "implied_margin")
                ):
                    raise SemanticError("handoff valuation available state has no value")
            expected_manifest = sorted(
                set(handoff["global_evidence_refs"])
                | {
                    evidence
                    for candidate in sorted(handoff["candidate_evidence_refs"])
                    for evidence in handoff["candidate_evidence_refs"][candidate]
                }
            )
            if handoff["evidence_manifest"] != expected_manifest:
                raise SemanticError("handoff evidence manifest union mismatch")
            for evidence_id in handoff["global_evidence_refs"]:
                evidence = evidence_registry.get(evidence_id)
                if evidence is None or evidence["candidate_id"] is not None:
                    raise SemanticError("handoff global evidence identity mismatch")
            for candidate, evidence_ids in handoff["candidate_evidence_refs"].items():
                for evidence_id in evidence_ids:
                    evidence = evidence_registry.get(evidence_id)
                    if evidence is None or evidence["candidate_id"] != candidate:
                        raise SemanticError("handoff candidate evidence identity mismatch")
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
            previous_generation = None
            if expected_mode == "update" and entry["artifacts"]:
                previous_generation = entry["artifacts"][0]["payload"]["update_diff"][
                    "old_generation"
                ]["generation_id"]
            historical_handoff = next(
                (
                    handoff_id
                    for handoff_id, handoff in state["handoff_history"].items()
                    if handoff["generation_id"] == previous_generation
                ),
                None,
            )
            temporary = {
                **state,
                "active_generation_id": generation_id,
                "generation_id": generation_id,
                "candidate_set_id": entry["candidate_set_id"],
                "comparison_as_of": entry["comparison_as_of"],
                "source_cutoff_at": entry["source_cutoff_at"],
                "previous_generation_id": previous_generation,
                "active_handoff_id": historical_handoff,
                "handoff_history": {
                    handoff_id: handoff
                    for handoff_id, handoff in state["handoff_history"].items()
                    if handoff["generation_id"] != generation_id
                },
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
                validate_phase_artifact(temporary, artifact)
                temporary["generation_history"][generation_id]["artifacts"].append(artifact)
