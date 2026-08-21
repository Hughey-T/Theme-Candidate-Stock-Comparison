from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_action_diagnostic_openapi.py"


def test_diagnostic_openapi_exposes_only_health_probe(tmp_path: Path) -> None:
    output = tmp_path / "diagnostic.json"
    subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--server-url",
            "https://theme.example.co.jp/theme-compare",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    document = json.loads(output.read_text(encoding="utf-8"))

    assert set(document["paths"]) == {"/health"}
    operation = document["paths"]["/health"]["get"]
    assert operation["operationId"] == "runDiagnosticProbe"
    assert document["servers"] == [{"url": "https://theme.example.co.jp/theme-compare"}]
    assert document["security"] == []
    assert operation["security"] == []
    assert "RUN" in operation["summary"]
    assert "Do not ask what to run" in operation["description"]
    assert operation["parameters"] == [
        {
            "name": "diagnostic_probe",
            "in": "query",
            "required": True,
            "description": "Always use the only allowed marker value for this diagnostic probe.",
            "schema": {"type": "string", "enum": ["custom-gpt-diagnostic-v1"]},
        }
    ]
