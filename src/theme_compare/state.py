"""Persisted state machine: no conversational or hidden-memory state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import INITIAL_PHASES, UPDATE_PHASES
from .models import SemanticError
from .validation import validate_envelope


class StateMachine:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        state: dict[str, Any] = json.loads(self.path.read_text())
        validate_envelope({**state, "artifacts": state.get("artifacts", [])})
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
            if artifact is None or artifact["generation_id"] == state["generation_id"]:
                raise SemanticError("update requires a new generation")
            state.update(
                mode="update",
                generation_id=artifact["generation_id"],
                candidate_set_id=artifact["candidate_set_id"],
                current_phase=1,
                completed_phases=[],
                status="in_progress",
                artifacts=[],
            )
        else:
            if state["status"] == "complete":
                raise SemanticError("analysis is already complete")
            phase = state["current_phase"]
            if artifact is None or artifact["phase"] != phase:
                raise SemanticError("phase skip, replay, or wrong artifact")
            validate_envelope({**state, "artifacts": [artifact]})
            state["artifacts"].append(artifact)
            state["completed_phases"].append(phase)
            maximum = INITIAL_PHASES if state["mode"] == "initial" else UPDATE_PHASES
            if phase == maximum:
                state["status"] = "complete"
            else:
                state["current_phase"] += 1
        self._atomic_write(state)
        return state

    def _atomic_write(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(self.path)
