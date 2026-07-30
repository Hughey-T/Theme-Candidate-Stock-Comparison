import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from phase_fixtures import artifact as valid_artifact
from theme_compare.schema_runtime import schema_bytes

ROOT = Path(__file__).parents[1]


def test_runtime_reads_packaged_schema_resource():
    assert json.loads(schema_bytes("phase-artifact"))["oneOf"]


@pytest.mark.parametrize("path", sorted((ROOT / "schemas").glob("*.json")))
def test_schema_is_valid_and_closed(path):
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    branches = schema.get("oneOf", [schema])
    assert all(
        branch.get("type") == "object" and branch.get("additionalProperties") is False
        for branch in branches
    )

    def assert_closed(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False
            for value in node.values():
                assert_closed(value)
        elif isinstance(node, list):
            for value in node:
                assert_closed(value)

    assert_closed(schema)


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


@pytest.mark.parametrize(
    "phase,mode,field",
    [
        (1, "initial", "session_and_candidates"),
        (2, "initial", "business_models"),
        (3, "initial", "theme_value_capture"),
        (4, "initial", "competitive_structure"),
        (5, "initial", "financial_conversion"),
        (6, "initial", "valuation_expectations"),
        (7, "initial", "common_scenarios"),
        (8, "initial", "catalysts"),
        (9, "initial", "risks_and_stress"),
        (10, "initial", "final_selection"),
        (1, "update", "update_diff"),
        (2, "update", "updated_selection"),
    ],
)
def test_each_phase_contract_accepts_only_its_payload(phase, mode, field):
    schema = json.loads((ROOT / "schemas/phase-artifact.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    document = valid_artifact(
        phase,
        "g2" if mode == "update" else "g1",
        mode,
        "2025-01-31T00:00:00Z" if mode == "update" else "2025-01-01T00:00:00Z",
    )
    assert not list(validator.iter_errors(document))
    bad = json.loads(json.dumps(document))
    bad["payload"][field]["arbitrary"] = True
    assert list(validator.iter_errors(bad))
    empty = json.loads(json.dumps(document))
    empty["payload"][field] = {}
    assert list(validator.iter_errors(empty))


def test_candidate_level_no_selection_rejected_by_schema():
    schema = json.loads((ROOT / "schemas/final-selection.schema.json").read_text())
    document = {
        "classifications": [{"candidate_id": "A", "classification": "NO_SELECTION"}],
        "overall_decision": "NO_SELECTION",
        "hard_gates": {},
    }
    assert list(Draft202012Validator(schema).iter_errors(document))


@pytest.mark.parametrize(
    "mutation",
    ["required", "wrong_type", "wrong_phase_payload", "candidate_count", "phase10_incomplete"],
)
def test_phase_internal_contract_mutations(mutation):
    schema = json.loads((ROOT / "schemas/phase-artifact.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    phase = 10 if mutation == "phase10_incomplete" else 1
    document = valid_artifact(phase)
    value = next(v for k, v in document["payload"].items() if k != "summary")
    if mutation == "required":
        value.pop(next(iter(value)))
    elif mutation == "wrong_type":
        value[next(iter(value))] = 123
    elif mutation == "wrong_phase_payload":
        document["payload"] = valid_artifact(7)["payload"]
    elif mutation == "candidate_count":
        value["candidate_inputs"] = []
    else:
        value.pop("scenario_results")
    assert list(validator.iter_errors(document))
