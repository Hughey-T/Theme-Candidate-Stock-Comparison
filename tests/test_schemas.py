import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("path", sorted((ROOT / "schemas").glob("*.json")))
def test_schema_is_valid_and_closed(path):
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False


def test_unknown_property_rejected():
    schema = json.loads((ROOT / "schemas/normalized-candidate.schema.json").read_text())
    document = {
        key: (
            False
            if spec.get("type") == "boolean"
            else []
            if spec.get("type") == "array"
            else None
            if isinstance(spec.get("type"), list)
            else "x"
        )
        for key, spec in schema["properties"].items()
    }
    document["unknown"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(document)


def test_timezone_missing_rejected():
    schema = json.loads((ROOT / "schemas/session-state.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(
        validator.iter_errors(
            {
                "mode": "initial",
                "session_id": "s",
                "generation_id": "g",
                "candidate_set_id": "c",
                "comparison_as_of": "2025-01-01T00:00:00",
                "source_cutoff_at": "2025-01-01T00:00:00",
                "current_phase": 1,
                "completed_phases": [],
                "status": "in_progress",
                "persistence_status": "not_generated",
                "artifacts": [],
            }
        )
    )


def test_generated_schemas_are_current(tmp_path):
    before = {p.name: p.read_bytes() for p in (ROOT / "schemas").glob("*.json")}
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "tools/generate_schemas.py"],
        cwd=ROOT,
        check=True,
        env={"PYTHONPATH": "src"},
    )
    assert before == {p.name: p.read_bytes() for p in (ROOT / "schemas").glob("*.json")}
