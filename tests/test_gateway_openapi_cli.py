from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_action_openapi.py"


def generate(tmp_path: Path) -> dict[str, object]:
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
    return json.loads(output.read_text(encoding="utf-8"))


def test_gateway_prefixed_server_url_is_emitted(tmp_path: Path) -> None:
    document = generate(tmp_path)
    public_url = "https://stable.ngrok-free.dev/theme-compare"
    assert document["servers"] == [{"url": public_url}]
    assert "/v2/sessions" in document["paths"]
    assert all(not path.startswith("/theme-compare/") for path in document["paths"])


def test_generated_action_datetime_fields_require_explicit_timezone(tmp_path: Path) -> None:
    document = generate(tmp_path)
    create = document["components"]["schemas"]["CreateBlindComparisonSessionV2Request"]
    update = document["components"]["schemas"]["StartBlindComparisonUpdateV2Request"]

    for schema in (create, update):
        for field in ("analysis_as_of", "source_cutoff_at"):
            timestamp = schema["properties"][field]
            assert timestamp["format"] == "date-time"
            assert "timezone" in timestamp["description"]
            pattern = re.compile(timestamp["pattern"])
            assert pattern.fullmatch("2026-08-22T00:00:00Z")
            assert pattern.fullmatch("2026-08-22T09:00:00+09:00")
            assert not pattern.fullmatch("2026-08-22")

    phase_information = document["components"]["schemas"]["BlindPhaseInformation"]
    phase_as_of = phase_information["properties"]["as_of"]
    assert "timezone" in phase_as_of["description"]
    assert not re.fullmatch(phase_as_of["pattern"], "2026-08-22")


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
