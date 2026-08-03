"""Preferred 2.0 blind-comparison protocol.

The conversational model supplies research and ordinal judgments.  This module
only owns disclosure, identities, progression, immutability and persistence.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from .models import SemanticError, candidate_set_id, parse_rfc3339, strict_json_loads
from .storage import JsonVolumeStorage

INITIAL_PHASES = 12
UPDATE_PHASES = 4
TAXONOMY = {
    "FACTS",
    "COMPANY_CLAIMS",
    "EXTERNAL_ESTIMATES",
    "AI_ASSUMPTIONS",
    "JUDGMENTS",
    "UNRESOLVED",
}
RANKING_KINDS = {
    "evidence_only_mechanical",
    "scenario_derived",
    "independent_ai",
    "integrated",
}


def _closed(value: dict[str, Any], allowed: set[str], name: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise SemanticError(f"unexpected {name} properties: {sorted(extra)}")


class V2RuntimeService:
    """Atomic v2 state store, isolated from read-only v1 sessions."""

    def __init__(self, storage: JsonVolumeStorage) -> None:
        self.storage = storage

    def _path(self, session_id: str) -> Path:
        return self.storage.path(session_id).with_suffix(".v2.json")

    def _load(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        if not path.is_file():
            raise FileNotFoundError(session_id)
        state = strict_json_loads(path.read_bytes())
        if not isinstance(state, dict) or state.get("contract_version") != "2.0.0":
            raise SemanticError("invalid v2 persisted state")
        return state

    def _write(self, session_id: str, state: dict[str, Any]) -> None:
        path = self._path(session_id)
        fd, name = tempfile.mkstemp(prefix=f".{session_id}.", dir=self.storage.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            if self._load(session_id) != state:
                raise SemanticError("atomic readback verification failed")
        finally:
            Path(name).unlink(missing_ok=True)

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        _closed(
            body,
            {
                "contract_version",
                "mode",
                "theme",
                "analysis_as_of",
                "source_cutoff_at",
                "candidates",
                "horizons",
                "blind_handoff",
                "reconciliation_handoff",
            },
            "session",
        )
        if body.get("contract_version") != "2.0.0" or body.get("mode") not in {
            "standalone",
            "pipeline",
        }:
            raise SemanticError("contract_version 2.0.0 and a supported mode are required")
        candidates = body.get("candidates", [])
        if len(candidates) > 12:
            raise SemanticError("initial candidate limit is 12")
        ids = [c["candidate_id"] for c in candidates]
        if len(ids) != len(set(ids)):
            raise SemanticError("duplicate candidate")
        cutoff = parse_rfc3339(body["source_cutoff_at"])
        if cutoff > parse_rfc3339(body["analysis_as_of"]):
            raise SemanticError("future evidence cutoff")
        horizons = body.get("horizons", [])
        if not horizons or len({h["horizon_id"] for h in horizons}) != len(horizons):
            raise SemanticError("unique horizon contracts are required")
        for horizon in horizons:
            if horizon["minimum_months"] > horizon["maximum_months"]:
                raise SemanticError("invalid horizon range")
        sid = "s_" + uuid.uuid4().hex
        ordered = sorted(candidates, key=lambda row: row["candidate_id"].casefold())
        set_id = candidate_set_id(candidates)
        state = {
            "contract_version": "2.0.0",
            "session_id": sid,
            "input_mode": body["mode"],
            "workflow": "initial",
            "phase": 1,
            "status": "in_progress",
            "generation_id": "g1",
            "analysis_as_of": body["analysis_as_of"],
            "source_cutoff_at": body["source_cutoff_at"],
            "theme": body["theme"],
            "horizons": horizons,
            "blind_order": [c["candidate_id"] for c in ordered],
            "candidate_sets": {
                "initial_candidate_set": set_id,
                "eligible_candidate_set": None,
                "deep_comparison_set": None,
                "final_selection_set": None,
            },
            "candidates": ordered,
            "artifacts": [],
            "independent_ai_frozen": False,
            "independent_ai_hash": None,
            "reconciliation_disclosed": False,
            "upstream_reconciliation": body.get("reconciliation_handoff"),
            "handoffs": {"blind": None, "reconciliation": None},
            "handoff_reconciled": False,
            "ledger": [],
            "generation_history": [],
            "persistence_status": "integrity_verified",
        }
        with self.storage.locked(sid):
            self._write(sid, state)
        return {
            "accepted": True,
            "session_id": sid,
            "generation_id": "g1",
            "next_phase": 1,
            "candidate_order": state["blind_order"],
            "contract_version": "2.0.0",
        }

    def contract(self, sid: str) -> dict[str, Any]:
        state = self._load(sid)
        if state["status"] == "complete":
            raise SemanticError("generation complete")
        result = {
            "workflow": state["workflow"],
            "phase": state["phase"],
            "generation_id": state["generation_id"],
            "candidate_order": state["blind_order"],
            "horizons": state["horizons"],
            "mechanical_rankings_disclosed": False,
        }
        # No ranking, score, previous conclusion, or persuasive upstream data crosses this boundary.
        if state["workflow"] == "initial" and state["phase"] >= 11:
            result["mechanical_rankings_disclosed"] = True
            result["reconciliation_available"] = state["independent_ai_frozen"]
        return result

    def submit(self, sid: str, artifact: dict[str, Any]) -> dict[str, Any]:
        state = self._load(sid)
        _closed(artifact, {"generation_id", "phase", "information", "payload"}, "artifact")
        if state["status"] == "complete" or artifact.get("phase") != state["phase"]:
            raise SemanticError("phase skip, replay, or final phase submission")
        if artifact.get("generation_id") != state["generation_id"]:
            raise SemanticError("mixed generation")
        information = artifact.get("information", [])
        for record in information:
            if record.get("classification") not in TAXONOMY:
                raise SemanticError("invalid information taxonomy")
            if parse_rfc3339(record["as_of"]) > parse_rfc3339(state["source_cutoff_at"]):
                raise SemanticError("future evidence")
            owner = record.get("candidate_id")
            if owner is not None and owner not in state["blind_order"]:
                raise SemanticError("cross-candidate or unknown evidence owner")
        payload = artifact.get("payload", {})
        phase = state["phase"]
        if state["workflow"] == "initial" and phase == 2:
            self._candidate_transition(state, payload, "eligible_candidate_set", 8)
        if state["workflow"] == "initial" and phase == 6:
            self._candidate_transition(state, payload, "deep_comparison_set", 5)
        freeze_phase = 10 if state["workflow"] == "initial" else 2
        reconcile_phase = 11 if state["workflow"] == "initial" else 3
        final_phase = 12 if state["workflow"] == "initial" else 4
        if phase == freeze_phase:
            if "independent_ai_ranking" not in payload:
                raise SemanticError("independent AI ranking required")
            state["independent_ai_frozen"] = True
            state["independent_ai_hash"] = self._hash(payload["independent_ai_ranking"])
        if phase == reconcile_phase:
            if not state["independent_ai_frozen"]:
                raise SemanticError("blind ranking must be frozen first")
            self._validate_phase11(state, payload)
            state["reconciliation_disclosed"] = True
        if phase == final_phase:
            self._finalize(state, payload)
        state["artifacts"].append(artifact)
        maximum = INITIAL_PHASES if state["workflow"] == "initial" else UPDATE_PHASES
        if phase == maximum:
            state["status"] = "complete"
        else:
            state["phase"] += 1
        with self.storage.locked(sid):
            self._write(sid, state)
        return {
            "accepted": True,
            "completed_phase": phase,
            "status": state["status"],
            "next_phase": None if state["status"] == "complete" else state["phase"],
            "persistence_status": "integrity_verified",
        }

    def start_update(self, sid: str, body: dict[str, Any]) -> dict[str, Any]:
        _closed(
            body,
            {"new_generation_id", "analysis_as_of", "source_cutoff_at", "candidates"},
            "update",
        )
        state = self._load(sid)
        if state["status"] != "complete":
            raise SemanticError("update requires completed generation")
        new_cutoff = parse_rfc3339(body["source_cutoff_at"])
        if new_cutoff <= parse_rfc3339(state["source_cutoff_at"]):
            raise SemanticError("update cutoff must be a strictly later UTC instant")
        if new_cutoff > parse_rfc3339(body["analysis_as_of"]):
            raise SemanticError("future cutoff")
        candidates = body["candidates"]
        if len(candidates) > 12 or len({c["candidate_id"] for c in candidates}) != len(candidates):
            raise SemanticError("invalid update candidates")
        state["generation_history"].append(
            {
                "generation_id": state["generation_id"],
                "artifacts": state["artifacts"],
                "candidate_sets": state["candidate_sets"],
                "ledger": state["ledger"],
                "handoffs": state["handoffs"],
            }
        )
        state.update(
            workflow="update",
            phase=1,
            status="in_progress",
            generation_id=body["new_generation_id"],
            analysis_as_of=body["analysis_as_of"],
            source_cutoff_at=body["source_cutoff_at"],
            candidates=sorted(candidates, key=lambda row: row["candidate_id"].casefold()),
            blind_order=sorted(c["candidate_id"] for c in candidates),
            artifacts=[],
            independent_ai_frozen=False,
            independent_ai_hash=None,
            reconciliation_disclosed=False,
            handoff_reconciled=False,
        )
        state["candidate_sets"] = {
            "initial_candidate_set": candidate_set_id(candidates),
            "eligible_candidate_set": None,
            "deep_comparison_set": None,
            "final_selection_set": None,
        }
        with self.storage.locked(sid):
            self._write(sid, state)
        return {"accepted": True, "generation_id": state["generation_id"], "next_phase": 1}

    @staticmethod
    def _hash(value: Any) -> str:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return hashlib.sha256(raw).hexdigest()

    def _candidate_transition(
        self, state: dict[str, Any], payload: dict[str, Any], name: str, limit: int
    ) -> None:
        rows = payload.get(name)
        if not isinstance(rows, list) or len(rows) > limit or len(rows) != len(set(rows)):
            raise SemanticError(f"invalid {name}")
        if not set(rows) <= set(state["blind_order"]):
            raise SemanticError("unknown candidate transition")
        selected = [c for c in state["candidates"] if c["candidate_id"] in rows]
        state["candidate_sets"][name] = candidate_set_id(selected) if selected else "EMPTY"

    def _validate_phase11(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        if self._hash(payload.get("independent_ai_ranking")) != state["independent_ai_hash"]:
            raise SemanticError("independent AI ranking is immutable")
        rankings = payload.get("rankings", {})
        if set(rankings) != {"evidence_only_mechanical", "scenario_derived"}:
            raise SemanticError("mechanical and scenario rankings must remain separate")
        for item in rankings["evidence_only_mechanical"].get("inputs", []):
            if item.get("classification") not in {"FACTS", "EXTERNAL_ESTIMATES"}:
                raise SemanticError("evidence-only mechanical input contamination")
        deep = payload.get("deep_candidates", [])
        expected = {tuple(sorted(pair)) for pair in combinations(deep, 2)}
        actual = {
            tuple(sorted((p["candidate_a"], p["candidate_b"]))) for p in payload.get("pairwise", [])
        }
        if expected != actual:
            raise SemanticError("incomplete unordered pair coverage")

    def _finalize(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        if not state["reconciliation_disclosed"]:
            raise SemanticError("reconciliation disclosure required")
        decision = payload.get("integrated_selection", {})
        selected = decision.get("selected_candidates", [])
        if len(selected) > 2 or not set(selected) <= set(state["blind_order"]):
            raise SemanticError("handoff candidate limit or identity mismatch")
        gates = decision.get("hard_gates", {})
        if any(gates.get(candidate) for candidate in selected):
            raise SemanticError("hard gate cannot be offset or overridden")
        expected = "NO_SELECTION" if not selected else "SELECTION"
        if decision.get("decision") != expected:
            raise SemanticError("selection/result mismatch")
        chosen = [c for c in state["candidates"] if c["candidate_id"] in selected]
        state["candidate_sets"]["final_selection_set"] = (
            candidate_set_id(chosen) if chosen else "EMPTY"
        )
        # Blind handoff intentionally contains no ranks, probabilities or persuasive rationale.
        state["handoffs"]["blind"] = {
            "candidates": chosen,
            "analysis_as_of": state["analysis_as_of"],
            "source_cutoff_at": state["source_cutoff_at"],
            "horizons": state["horizons"],
            "unresolved_factual_questions": payload.get("unresolved_factual_questions", []),
        }
        state["handoffs"]["reconciliation"] = payload.get("reconciliation_handoff")
        state["ledger"] = payload.get("decision_ledger", [])

    def disclose(self, sid: str) -> dict[str, Any]:
        state = self._load(sid)
        if not state["independent_ai_frozen"]:
            raise SemanticError("reconciliation unavailable before Phase 10 freeze")
        return {
            "upstream_reconciliation": state["upstream_reconciliation"],
            "independent_ai_hash": state["independent_ai_hash"],
        }

    def handoff(self, sid: str, reconciliation: bool) -> dict[str, Any]:
        state = self._load(sid)
        if state["status"] != "complete":
            raise SemanticError("handoff unavailable")
        if reconciliation and not state["handoff_reconciled"]:
            raise SemanticError("blind individual analysis must be acknowledged first")
        return cast(
            dict[str, Any],
            state["handoffs"]["reconciliation" if reconciliation else "blind"],
        )

    def acknowledge_blind(self, sid: str) -> dict[str, Any]:
        state = self._load(sid)
        state["handoff_reconciled"] = True
        with self.storage.locked(sid):
            self._write(sid, state)
        return {"accepted": True}
