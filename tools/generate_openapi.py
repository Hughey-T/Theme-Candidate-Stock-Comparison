"""Deprecated wrapper for the canonical v2-only Action OpenAPI generator."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
    module = importlib.import_module("theme_compare.action_openapi")
    module.main()


if __name__ == "__main__":
    main()
