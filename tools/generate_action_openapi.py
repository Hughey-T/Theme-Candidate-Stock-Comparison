"""CLI wrapper for the canonical Action OpenAPI generator.

The runtime contract stays canonical in ``theme_compare.action_openapi``. This wrapper
adds support for a stable reverse-proxy path prefix such as ``/theme-compare`` by
building the canonical document for the HTTPS origin and then setting the OpenAPI
server URL to the validated public base path.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

_SAFE_PREFIX = re.compile(r"^/[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*$")
_RFC3339_INSTANT_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
_RFC3339_INSTANT_DESCRIPTION = (
    "RFC 3339 instant with an explicit timezone suffix (Z or ±HH:MM). "
    "Bare calendar dates such as 2026-08-22 are invalid."
)


def split_public_server_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("server URL must be an absolute https URL")
    if parsed.query or parsed.fragment or parsed.params:
        raise ValueError("server URL must not contain params/query/fragment")

    path = parsed.path.rstrip("/")
    if path and not _SAFE_PREFIX.fullmatch(path):
        raise ValueError("server URL path must contain lowercase slug segments only")

    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    public_base = origin + path
    return origin, public_base


def harden_action_datetime_schemas(value: object) -> None:
    """Mirror the runtime's timezone-aware RFC3339 requirement in Action schemas."""
    if isinstance(value, dict):
        if value.get("type") == "string" and value.get("format") == "date-time":
            value["pattern"] = _RFC3339_INSTANT_PATTERN
            existing = value.get("description")
            if isinstance(existing, str) and existing:
                value["description"] = existing + " " + _RFC3339_INSTANT_DESCRIPTION
            else:
                value["description"] = _RFC3339_INSTANT_DESCRIPTION
        for item in value.values():
            harden_action_datetime_schemas(item)
    elif isinstance(value, list):
        for item in value:
            harden_action_datetime_schemas(item)


def main() -> None:
    sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
    module = importlib.import_module("theme_compare.action_openapi")

    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--output", type=Path, default=module.DEFAULT_OUTPUT)
    args = parser.parse_args()

    origin, public_base = split_public_server_url(args.server_url)
    origin = module.validate_server_url(origin)
    document = module.build_document(origin)
    harden_action_datetime_schemas(document)
    document["servers"] = [{"url": public_base}]

    encoded = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
