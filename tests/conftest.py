from __future__ import annotations

import pytest

from theme_compare.models import candidate_set_id


@pytest.fixture
def candidates():
    rows = []
    for ticker in ("AAA", "BBB", "CCC"):
        rows.append(
            {
                "candidate_id": f"US-XNAS-{ticker}-common",
                "issuer_id": f"lei-{ticker}",
                "issuer_name": ticker,
                "ticker": ticker,
                "exchange": "XNAS",
                "share_class": "common",
                "is_adr": False,
                "underlying_security_id": None,
                "former_tickers": [],
                "corporate_action_lineage": [],
                "listing_country": "US",
            }
        )
    return rows, candidate_set_id(rows)


@pytest.fixture
def judgments():
    return [
        {
            "judgment": "attractive",
            "evidence_refs": ["E1"],
            "contrary_evidence_refs": ["E2"],
            "confidence": "medium",
            "assumptions": ["demand"],
            "invalidation_conditions": ["demand falls"],
        }
    ]
