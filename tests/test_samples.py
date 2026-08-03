import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
VALID = {
    "same-industry-5",
    "mixed-business-models",
    "primary-secondary",
    "conditional-only",
    "no-selection",
    "update-primary-change",
    "update-no-change",
    "v2-blind-session",
}
INVALID = {
    "mixed-generation",
    "candidate-duplicate",
    "probability-total",
    "ranking-mismatch",
    "noncomparable-scored",
    "hard-gate-bypass",
    "future-information",
    "hash-mismatch",
    "invalid-data-state",
    "timezone-missing",
    "handoff-mismatch",
}


def test_sample_catalogue():
    valid = {p.stem for p in (ROOT / "samples/valid").glob("*.json")}
    invalid = {p.stem for p in (ROOT / "samples/invalid").glob("*.json")}
    assert valid == VALID and invalid == INVALID
    for path in (ROOT / "samples").glob("*/*.json"):
        value = json.loads(path.read_text())
        assert value["expected_valid"] == (path.parent.name == "valid")
