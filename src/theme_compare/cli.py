"""CLI for schema and semantic validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("schema", type=Path)
    parser.add_argument("document", type=Path)
    args = parser.parse_args()
    schema = json.loads(args.schema.read_text())
    document = json.loads(args.document.read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    print("valid")


if __name__ == "__main__":
    main()
