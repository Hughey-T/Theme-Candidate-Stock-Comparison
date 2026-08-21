from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_action_diagnostic_openapi.py"


def test_diagnostic_openapi_exposes_only_create_action(tmp_path: Path) -> None:
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

    assert set(document["paths"]) == {"/v2/sessions"}
    operation = document["paths"]["/v2/sessions"]["post"]
    assert operation["operationId"] == "createBlindComparisonSessionV2"
    assert document["servers"] == [{"url": "https://theme.example.co.jp/theme-compare"}]
    assert operation["parameters"][0]["name"] == "idempotency_key"
    assert operation["parameters"][0]["in"] == "query"
    assert operation["parameters"][0]["required"] is True
