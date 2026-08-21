"""Generate a one-operation Custom GPT Action contract for invocation diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_action_openapi import split_public_server_url  # noqa: E402
from theme_compare.action_openapi import build_document  # noqa: E402

DEFAULT_OUTPUT = Path("openapi/custom-gpt-action.diagnostic.openapi.json")
TARGET_PATH = "/v2/sessions"


def build_diagnostic_document(server_url: str) -> dict[str, object]:
    origin, public_base = split_public_server_url(server_url)
    document = build_document(origin)
    operation = document["paths"][TARGET_PATH]
    document["paths"] = {TARGET_PATH: operation}
    document["servers"] = [{"url": public_base}]
    info = document["info"]
    if isinstance(info, dict):
        info["title"] = "Theme Candidate Stock Comparison Action Diagnostic"
        info["description"] = (
            "Temporary one-operation Action contract used only to verify that "
            "Custom GPT actually invokes createBlindComparisonSessionV2."
        )
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    document = build_diagnostic_document(args.server_url)
    encoded = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
