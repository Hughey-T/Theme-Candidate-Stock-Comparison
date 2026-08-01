"""Generate the Custom GPT Actions document from packaged contracts."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
OPENAPI_PATH = ROOT / "openapi" / "custom-gpt-action.openapi.yaml"
SCHEMA_ROOT = ROOT / "src" / "theme_compare" / "schemas"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parameter_key(parameter: dict[str, Any]) -> tuple[Any, Any]:
    return parameter.get("name"), parameter.get("in")


def move_path_parameters_to_operations(document: dict[str, Any]) -> None:
    for path, path_item in document["paths"].items():
        inherited = path_item.pop("parameters", [])
        operations = [
            operation for method, operation in path_item.items() if method in HTTP_METHODS
        ]
        for operation in operations:
            existing = operation.get("parameters", [])
            merged: list[dict[str, Any]] = []
            seen: set[tuple[Any, Any]] = set()
            for parameter in [*inherited, *existing]:
                key = parameter_key(parameter)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(deepcopy(parameter))
            if "{session_id}" in path:
                session_parameters = [
                    parameter
                    for parameter in merged
                    if parameter_key(parameter) == ("session_id", "path")
                ]
                if len(session_parameters) != 1:
                    raise ValueError(f"{path} must define exactly one session_id path parameter")
                session_parameter = session_parameters[0]
                merged = [
                    parameter
                    for parameter in merged
                    if parameter_key(parameter) != ("session_id", "path")
                ]
                merged.insert(0, session_parameter)
            if merged:
                operation["parameters"] = merged
            else:
                operation.pop("parameters", None)


def main() -> None:
    document = load_json(OPENAPI_PATH)
    components = document["components"]["schemas"]
    components["CreateSessionRequest"] = load_json(
        SCHEMA_ROOT / "upstream-theme-handoff.schema.json"
    )
    components["PhaseArtifact"] = load_json(SCHEMA_ROOT / "phase-artifact.schema.json")
    move_path_parameters_to_operations(document)
    OPENAPI_PATH.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
