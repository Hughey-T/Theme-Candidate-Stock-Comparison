"""Mandatory in-process JSON Schema validation for runtime boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .models import SemanticError

SCHEMA_ROOT = Path(__file__).parents[2] / "schemas"


def validate_document(name: str, document: Any) -> None:
    schema = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        location = "/".join(str(item) for item in errors[0].absolute_path)
        raise SemanticError(f"{name} schema violation at {location}: {errors[0].message}")
