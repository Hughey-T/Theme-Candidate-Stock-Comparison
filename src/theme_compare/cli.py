"""CLI for validation and private-runtime administration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .models import strict_json_loads
from .runtime import RuntimeService
from .schema_runtime import validate_document
from .storage import JsonVolumeStorage


def _service(root: str | None) -> RuntimeService:
    return RuntimeService(
        JsonVolumeStorage(
            Path(root or os.environ.get("THEME_COMPARE_STORAGE_ROOT", "/data/sessions"))
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="theme-compare")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    for name in ("create-session", "show-session", "validate-state", "export-handoff"):
        command = sub.add_parser(name)
        command.add_argument("value")
        command.add_argument("--storage-root")
        if name == "export-handoff":
            command.add_argument("--history", action="store_true")
    parser.add_argument("schema", type=Path, nargs="?")
    parser.add_argument("document", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("theme_compare.api:app_factory", host=args.host, port=args.port, factory=True)
    elif args.command == "create-session":
        print(
            json.dumps(
                _service(args.storage_root).create(
                    strict_json_loads(Path(args.value).read_bytes())
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "show-session":
        print(
            json.dumps(
                _service(args.storage_root).summary(args.value), ensure_ascii=False, indent=2
            )
        )
    elif args.command == "validate-state":
        validate_document("session-state", strict_json_loads(Path(args.value).read_bytes()))
        print("valid")
    elif args.command == "export-handoff":
        print(
            json.dumps(
                _service(args.storage_root).handoff(args.value, args.history),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.schema and args.document:
        schema = strict_json_loads(args.schema.read_bytes())
        document = strict_json_loads(args.document.read_bytes())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
        print("valid")
    else:
        parser.error("provide a command, or SCHEMA DOCUMENT for legacy validation")


if __name__ == "__main__":
    main()
