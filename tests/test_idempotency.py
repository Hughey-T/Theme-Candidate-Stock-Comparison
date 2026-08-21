from __future__ import annotations

import pytest

from theme_compare.idempotency import IdempotencyStore
from theme_compare.models import SemanticError


def test_same_key_and_payload_replays_persisted_result(tmp_path):
    store = IdempotencyStore(tmp_path)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return {"accepted": True, "session_id": "s_" + "a" * 32}

    payload = {"contract_version": "2.0.0", "theme": "power"}
    first = store.execute("v2:create", "request-0001", payload, operation)
    second = IdempotencyStore(tmp_path).execute("v2:create", "request-0001", payload, operation)

    assert first == second
    assert calls == 1


def test_same_key_with_different_payload_is_rejected(tmp_path):
    store = IdempotencyStore(tmp_path)
    store.execute("v2:create", "request-0002", {"theme": "power"}, lambda: {"accepted": True})

    with pytest.raises(SemanticError, match="different payload"):
        store.execute("v2:create", "request-0002", {"theme": "semis"}, lambda: {"accepted": True})


def test_idempotency_key_has_bounded_length(tmp_path):
    store = IdempotencyStore(tmp_path)
    with pytest.raises(SemanticError, match="8..200"):
        store.execute("v2:create", "short", {}, lambda: {"accepted": True})
