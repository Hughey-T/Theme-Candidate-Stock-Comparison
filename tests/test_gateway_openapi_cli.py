from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_action_openapi.py"


def test_gateway_prefixed_server_url_is_emitted(tmp_path: Path) -> None:
    output = tmp_path / "action.json"
    public_url = "https://stable.ngrok-free.dev/theme-compare"
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--server-url",
            public_url,
            "--output",
            str(output),
        ],
        check=True,
        cwd=ROOT,
    )
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["servers"] == [{"url": public_url}]
    assert "/v2/sessions" in document["paths"]
    assert all(not path.startswith("/theme-compare/") for path in document["paths"])


@pytest.mark.parametrize(
    "url",
    [
        "https://stable.ngrok-free.dev/Theme-Compare",
        "https://stable.ngrok-free.dev/theme_compare",
        "https://stable.ngrok-free.dev/theme-compare?x=1",
        "https://stable.ngrok-free.dev/theme-compare#fragment",
    ],
)
def test_gateway_server_url_rejects_unsafe_prefixes(tmp_path: Path, url: str) -> None:
    output = tmp_path / "action.json"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--server-url", url, "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
