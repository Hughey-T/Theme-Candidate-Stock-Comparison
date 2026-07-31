"""CLI for schema and semantic validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .models import strict_json_loads


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("schema", type=Path)
    parser.add_argument("document", type=Path)
    args = parser.parse_args()
    schema = strict_json_loads(args.schema.read_bytes())
    document = strict_json_loads(args.document.read_bytes())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    print("valid")


if __name__ == "__main__":
    main()
