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
    document["servers"] = [{"url": public_base}]

    encoded = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
