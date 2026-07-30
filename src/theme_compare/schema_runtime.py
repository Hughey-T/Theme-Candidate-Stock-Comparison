"""Mandatory in-process JSON Schema validation using packaged resources."""

from __future__ import annotations
from importlib.resources import files
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from .models import SemanticError, strict_json_loads


def schema_bytes(name: str) -> bytes:
    return files("theme_compare.schemas").joinpath(f"{name}.schema.json").read_bytes()


def validate_document(name: str, document: Any) -> None:
    schema = strict_json_loads(schema_bytes(name))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda e: list(e.absolute_path),
    )
    if errors:
        location = "/".join(str(x) for x in errors[0].absolute_path)
        raise SemanticError(f"{name} schema violation at {location}: {errors[0].message}")
